#!/usr/bin/env python3
"""Run deterministic + stochastic playback for benchmark assignments.

Stochastic playback uses ``STOCHASTIC_FLAGS`` (50 samples, base seed 123, downtime probability
0.05, weather probability 0.1, landing-shock probability 0.05). Since FHOPS 1.0.1 each downtime hit
samples a duration from the ``fhops eval-playback`` defaults (mean 4 h, std 1.5 h, clipped to the
shift length; a full-shift loss cancels the assignment) instead of always removing the whole shift,
and landing shocks are sampled per landing and calendar day and scale every assignment on the
landing for their duration. Assets generated with FHOPS 1.0.0 therefore differ in the stochastic
outputs only (see ``docs/howto/evaluation.rst``, "Stochastic event semantics").

Install ``tabulate`` before running so ``summary.md`` contains Markdown tables (without it the
playback exporter falls back to CSV blocks and the committed summaries change).

``metrics.json`` (written by this script, not by ``eval-playback``) reports, per mode:

* ``samples``: number of playback samples (1 for deterministic runs);
* ``total_production``: terminal **delivered** volume (m³), i.e. the playback tracker's
  ``delivered_total`` (the same quantity as ``compute_kpis(...)["total_production"]`` and the
  benchmark ``kpi_total_production``); stochastic runs report the mean over samples and
  ``total_production_std`` the population standard deviation;
* ``remaining_work``: undelivered ``Block.work_required`` volume (m³), mean over samples;
* ``all_roles_production_units``: sum of ``production_units`` over every machine and role (the
  "Total production units" line of ``summary.md``); a volume handled by a feller, skidder,
  processor and loader is counted once per role, so this is not delivered volume;
* ``total_hours`` and ``mobilisation_cost``: worked hours and mobilisation cost (CAD), mean over
  samples;
* ``average_utilisation``: mean day-level utilisation over every day of every sample.

Before FHOPS 1.0.1 (#119) ``total_production`` was the all-roles sum, and ``total_hours`` /
``mobilisation_cost`` were summed over all 50 stochastic samples. Delivered volumes come from an
in-process replay of the same playback (same sampling configuration, built from the
``eval-playback`` defaults plus ``STOCHASTIC_OPTIONS``); the script checks that the replay's
day-level production and hours equal the CLI's ``day.csv`` before writing ``metrics.json``.
"""

from __future__ import annotations

import argparse
import inspect
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fhops.cli.main import eval_playback
from fhops.evaluation import (
    PlaybackConfig,
    SamplingConfig,
    day_dataframe,
    day_dataframe_from_ensemble,
    run_playback,
    run_stochastic_playback,
)
from fhops.evaluation.playback.adapters import normalise_shift_ids
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

SCENARIOS = [
    {
        "slug": "tiny7",
        "scenario": Path("examples/tiny7/scenario.yaml"),
        "solvers": [
            (
                "ils",
                Path("docs/softwarex/assets/data/benchmarks/tiny7/user-1/ils_assignments.csv"),
            ),
            ("sa", Path("docs/softwarex/assets/data/benchmarks/tiny7/user-1/sa_assignments.csv")),
        ],
    },
    {
        "slug": "med42",
        "scenario": Path("examples/med42/scenario.yaml"),
        "solvers": [
            ("ils", Path("docs/softwarex/assets/data/benchmarks/med42/user-1/ils_assignments.csv")),
            ("sa", Path("docs/softwarex/assets/data/benchmarks/med42/user-1/sa_assignments.csv")),
        ],
    },
    {
        "slug": "synthetic_small",
        "scenario": Path("docs/softwarex/assets/data/datasets/synthetic_small/scenario.yaml"),
        "solvers": [
            (
                "ils",
                Path(
                    "docs/softwarex/assets/data/benchmarks/synthetic_small/user-1/ils_assignments.csv"
                ),
            ),
            (
                "sa",
                Path(
                    "docs/softwarex/assets/data/benchmarks/synthetic_small/user-1/sa_assignments.csv"
                ),
            ),
        ],
    },
]

# Downtime duration uses the eval-playback defaults (--downtime-mean 4.0, --downtime-std 1.5) and the
# default base seed (--seed 123). Keys are eval-playback parameter names.
STOCHASTIC_OPTIONS: dict[str, tuple[str, int | float]] = {
    "samples": ("--samples", 50),
    "downtime_probability": ("--downtime-prob", 0.05),
    "weather_probability": ("--weather-prob", 0.1),
    "landing_probability": ("--landing-prob", 0.05),
}
STOCHASTIC_FLAGS = [
    str(item) for flag, value in STOCHASTIC_OPTIONS.values() for item in (flag, value)
]
REPLAY_TOLERANCE = 1e-6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="Path to FHOPS repository root.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Playback asset directory (defaults to docs/softwarex/assets/data/playback).",
    )
    return parser.parse_args()


def ensure_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)


def run_eval(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _cli_defaults() -> dict[str, Any]:
    """Return the ``eval-playback`` option defaults (Typer ``OptionInfo.default``)."""
    defaults: dict[str, Any] = {}
    for name, param in inspect.signature(eval_playback).parameters.items():
        default = getattr(param.default, "default", param.default)
        defaults[name] = default
    return defaults


def _sampling_config(options: dict[str, Any]) -> SamplingConfig:
    """Build the SamplingConfig exactly as ``fhops eval-playback`` does for ``options``."""
    cfg = SamplingConfig(samples=options["samples"], base_seed=options["base_seed"])
    cfg.downtime.enabled = options["downtime_probability"] > 0
    cfg.downtime.probability = options["downtime_probability"]
    cfg.downtime.max_concurrent = options["downtime_max_concurrent"]
    cfg.downtime.mean_duration_hours = options["downtime_mean_hours"]
    cfg.downtime.std_duration_hours = options["downtime_std_hours"]
    cfg.weather.enabled = options["weather_probability"] > 0
    cfg.weather.day_probability = options["weather_probability"]
    cfg.weather.severity_levels = {"default": options["weather_severity"]}
    cfg.weather.impact_window_days = options["weather_window"]
    cfg.landing.enabled = options["landing_probability"] > 0
    cfg.landing.probability = options["landing_probability"]
    cfg.landing.capacity_multiplier_range = (
        options["landing_multiplier_low"],
        options["landing_multiplier_high"],
    )
    cfg.landing.duration_days = options["landing_duration"]
    return cfg


def replay_delivered(
    scenario_path: Path, assignments_path: Path, stochastic: bool, day_csv: Path
) -> tuple[list[float], list[float]]:
    """Replay the playback in-process and return per-sample delivered/remaining volume (m³).

    Raises ``RuntimeError`` when the replay's day-level production or hours differ from the
    CLI-written ``day_csv`` (i.e. the in-process configuration drifted from ``eval-playback``).
    """
    options = _cli_defaults()
    if stochastic:
        options.update({name: value for name, (_, value) in STOCHASTIC_OPTIONS.items()})
    pb = Problem.from_scenario(load_scenario(str(scenario_path)))
    assignments = normalise_shift_ids(pb, pd.read_csv(assignments_path))
    if stochastic:
        ensemble = run_stochastic_playback(
            pb, assignments, sampling_config=_sampling_config(options)
        )
        results = [sample.result for sample in ensemble.samples]
        replay_day = day_dataframe_from_ensemble(ensemble)
    else:
        result = run_playback(
            pb, assignments, config=PlaybackConfig(include_idle_records=options["include_idle"])
        )
        results = [result]
        replay_day = day_dataframe(result)
    cli_day = pd.read_csv(day_csv)
    for col in ("production_units", "total_hours"):
        a = cli_day[col].to_numpy(dtype=float)
        b = replay_day[col].to_numpy(dtype=float)
        if a.shape != b.shape or bool((np.abs(a - b) > REPLAY_TOLERANCE).any()):
            raise RuntimeError(f"In-process playback replay differs from {day_csv} ({col}).")
    return (
        [float(r.delivered_total) for r in results],
        [float(r.remaining_work_total) for r in results],
    )


def summarize_metrics(
    day_csv: Path,
    dest: Path,
    delivered: list[float],
    remaining: list[float],
) -> None:
    """Write ``metrics.json`` (schema in the module docstring)."""
    day_df = pd.read_csv(day_csv)
    samples = int(day_df["sample_id"].nunique()) if "sample_id" in day_df.columns else 1
    samples = samples or 1
    if len(delivered) != samples:
        raise RuntimeError(f"{day_csv}: {samples} samples in day.csv, {len(delivered)} replayed.")
    delivered_arr = np.asarray(delivered, dtype=float)
    utilisation = day_df["utilisation_ratio"].dropna()
    metrics = {
        "samples": samples,
        "total_production": float(delivered_arr.mean()),
        "total_production_std": float(delivered_arr.std(ddof=0)),
        "remaining_work": float(np.mean(remaining)),
        "all_roles_production_units": float(day_df["production_units"].sum()) / samples,
        "total_hours": float(day_df["total_hours"].sum()) / samples,
        "mobilisation_cost": float(day_df["mobilisation_cost"].sum()) / samples,
        "average_utilisation": float(utilisation.mean()) if not utilisation.empty else 0.0,
    }
    dest.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")


def ensure_trailing_newline(path: Path) -> None:
    """Match the repository's end-of-file-fixer hook so regenerated assets are byte-stable."""
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        path.write_text(text + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = (
        args.out_dir
        if args.out_dir is not None
        else repo_root / "docs" / "softwarex" / "assets" / "data" / "playback"
    ).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    for cfg in SCENARIOS:
        slug = cfg["slug"]
        scenario_path = repo_root / cfg["scenario"]
        ensure_paths([scenario_path])
        for solver, assignments_rel in cfg["solvers"]:
            assignments_path = repo_root / assignments_rel
            ensure_paths([assignments_path])
            base_dir = out_dir / slug / solver
            for mode, extra_flags in (
                ("deterministic", []),
                ("stochastic", STOCHASTIC_FLAGS),
            ):
                mode_dir = base_dir / mode
                mode_dir.mkdir(parents=True, exist_ok=True)
                shift_csv = mode_dir / "shift.csv"
                day_csv = mode_dir / "day.csv"
                summary_md = mode_dir / "summary.md"
                cmd = [
                    sys.executable,
                    "-m",
                    "fhops.cli.main",
                    "eval-playback",
                    str(scenario_path),
                    "--assignments",
                    str(assignments_path),
                    "--shift-out",
                    str(shift_csv),
                    "--day-out",
                    str(day_csv),
                    "--summary-md",
                    str(summary_md),
                ]
                cmd.extend(extra_flags)
                print(f"[playback] {slug}/{solver} ({mode})")
                run_eval(cmd)
                ensure_trailing_newline(summary_md)
                delivered, remaining = replay_delivered(
                    scenario_path, assignments_path, mode == "stochastic", day_csv
                )
                summarize_metrics(day_csv, mode_dir / "metrics.json", delivered, remaining)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
