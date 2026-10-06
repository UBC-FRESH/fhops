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
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from fhops.evaluation.playback.exporters import playback_summary_metrics

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
# default base seed (--seed 123).
STOCHASTIC_FLAGS = [
    "--samples",
    "50",
    "--downtime-prob",
    "0.05",
    "--weather-prob",
    "0.1",
    "--landing-prob",
    "0.05",
]


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


def summarize_metrics(shift_csv: Path, day_csv: Path, dest: Path) -> None:
    shift_df = pd.read_csv(shift_csv)
    day_df = pd.read_csv(day_csv)
    metrics = playback_summary_metrics(shift_df, day_df)
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
                summarize_metrics(shift_csv, day_csv, mode_dir / "metrics.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
