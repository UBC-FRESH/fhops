#!/usr/bin/env python
"""Run multiple tuning strategies over scenario bundles and aggregate telemetry."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Sequence
import json
import sqlite3
from statistics import fmean
import pandas as pd
import typer

from fhops.cli.main import _collect_tuning_scenarios
from fhops.optimization.heuristics.ils import solve_ils
from fhops.optimization.heuristics.tabu import solve_tabu
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario

CLI_ENTRY_POINT = [sys.executable, "-m", "fhops.cli.main"]
ANALYZE_SCRIPT = [sys.executable, "scripts/analyze_tuner_reports.py"]

DEFAULT_RANDOM_RUNS = 3
DEFAULT_RANDOM_ITERS = 250
DEFAULT_GRID_ITERS = 250
DEFAULT_BAYES_TRIALS = 20
DEFAULT_BAYES_ITERS = 250
DEFAULT_GRID_BATCH_SIZES = [1, 2]
DEFAULT_GRID_PRESETS = ["balanced", "explore"]
DEFAULT_TUNERS = ["random", "grid", "bayes"]
DEFAULT_TIERS = ["short"]
DEFAULT_ILS_RUNS = 2
DEFAULT_ILS_ITERS = 250
DEFAULT_ILS_SEED = 321
DEFAULT_TABU_RUNS = 2
DEFAULT_TABU_ITERS = 1500
DEFAULT_TABU_SEED = 555

TIER_BUDGETS: dict[str, dict[str, object]] = {
    "short": {
        "random": {"runs": 2, "iters": 150},
        "grid": {"iters": 150, "batch_sizes": list(DEFAULT_GRID_BATCH_SIZES), "presets": list(DEFAULT_GRID_PRESETS)},
        "bayes": {"trials": 20, "iters": 150},
        "ils": {"runs": 2, "iters": 200, "perturbation_strength": 3, "stall_limit": 10},
        "tabu": {"runs": 2, "iters": 1200, "stall_limit": 150},
    },
    "medium": {
        "random": {"runs": 3, "iters": 300},
        "grid": {"iters": 300, "batch_sizes": list(DEFAULT_GRID_BATCH_SIZES), "presets": list(DEFAULT_GRID_PRESETS)},
        "bayes": {"trials": 40, "iters": 300},
        "ils": {"runs": 3, "iters": 350, "perturbation_strength": 3, "stall_limit": 12},
        "tabu": {"runs": 3, "iters": 2000, "stall_limit": 180},
    },
    "long": {
        "random": {"runs": 5, "iters": 600},
        "grid": {"iters": 600, "batch_sizes": list(DEFAULT_GRID_BATCH_SIZES), "presets": list(DEFAULT_GRID_PRESETS)},
        "bayes": {"trials": 75, "iters": 600},
        "ils": {"runs": 5, "iters": 700, "perturbation_strength": 4, "stall_limit": 15, "hybrid_use_mip": True},
        "tabu": {"runs": 5, "iters": 3000, "stall_limit": 220},
    },
}

BENCHMARK_PLANS: dict[str, dict[str, object]] = {
    "baseline-smoke": {
        "bundles": ["baseline"],
        "tiers": ["short"],
        "tuners": ["random", "grid", "bayes", "ils", "tabu"],
        "budgets": {
            "short": {
                "random": {"runs": 3, "iters": 250},
                "grid": {"iters": 250, "batch_sizes": [1, 2], "presets": ["balanced", "explore"]},
                "bayes": {"trials": 30, "iters": 250},
                "ils": {"runs": 2, "iters": 260, "perturbation_strength": 3, "stall_limit": 10},
                "tabu": {"runs": 2, "iters": 1600, "stall_limit": 160},
            }
        },
    },
    "synthetic-smoke": {
        "bundles": ["synthetic"],
        "tiers": ["short"],
        "tuners": ["random", "grid", "bayes", "ils", "tabu"],
        "budgets": {
            "short": {
                "random": {"runs": 3, "iters": 300},
                "grid": {"iters": 300, "batch_sizes": [1, 2], "presets": ["balanced", "explore"]},
                "bayes": {"trials": 30, "iters": 300},
                "ils": {"runs": 2, "iters": 320, "perturbation_strength": 3, "stall_limit": 12},
                "tabu": {"runs": 2, "iters": 1800, "stall_limit": 180},
            }
        },
    },
    "full-spectrum": {
        "bundles": ["baseline", "synthetic"],
        "tiers": ["short", "medium"],
        "tuners": ["random", "grid", "bayes", "ils", "tabu"],
        "budgets": {
            "short": {
                "random": {"runs": 3, "iters": 300},
                "grid": {"iters": 300, "batch_sizes": [1, 2], "presets": ["balanced", "explore"]},
                "bayes": {"trials": 30, "iters": 300},
                "ils": {"runs": 2, "iters": 320, "perturbation_strength": 3, "stall_limit": 12},
                "tabu": {"runs": 2, "iters": 1800, "stall_limit": 180},
            },
            "medium": {
                "random": {"runs": 4, "iters": 450},
                "grid": {"iters": 450, "batch_sizes": [1, 2], "presets": ["balanced", "explore"]},
                "bayes": {"trials": 45, "iters": 450},
                "ils": {"runs": 3, "iters": 520, "perturbation_strength": 3, "stall_limit": 14},
                "tabu": {"runs": 3, "iters": 2200, "stall_limit": 200},
            },
        },
    },
}


def _run(cmd: list[str], *, verbose: bool = False) -> None:
    if verbose:
        print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, text=True)


def _bundle_args(bundles: list[str]) -> list[str]:
    args: list[str] = []
    for bundle in bundles:
        args.extend(["--bundle", bundle])
    return args


def _scenario_args(scenarios: list[Path]) -> list[str]:
    args: list[str] = []
    for scenario in scenarios:
        args.append(str(scenario))
    return args


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        action="append",
        default=None,
        help="Scenario bundle alias or path (repeatable). Defaults to plan bundles or 'baseline'.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        type=Path,
        help="Explicit scenario YAML path (repeatable).",
    )
    parser.add_argument(
        "--plan",
        choices=sorted(BENCHMARK_PLANS.keys()),
        help="Named benchmark plan providing bundles and tuner budgets.",
    )
    parser.add_argument(
        "--tier",
        action="append",
        choices=sorted(TIER_BUDGETS.keys()),
        help="Budget tier(s) to execute (repeatable). Defaults to plan tiers or 'short'.",
    )
    parser.add_argument(
        "--tuner",
        action="append",
        choices=["random", "grid", "bayes", "ils", "tabu"],
        help="Subset of tuners to run (defaults to plan or all).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tmp/tuning-benchmarks"),
        help="Directory where telemetry and reports are written.",
    )
    parser.add_argument(
        "--telemetry-log",
        type=Path,
        help="Explicit telemetry log path. Defaults to <out-dir>/telemetry/runs.jsonl.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing telemetry log instead of starting fresh.",
    )
    parser.add_argument(
        "--random-runs",
        type=int,
        help="Number of random tuner runs per scenario.",
    )
    parser.add_argument(
        "--random-iters",
        type=int,
        help="Simulated annealing iterations per random tuner run.",
    )
    parser.add_argument(
        "--grid-iters",
        type=int,
        help="Simulated annealing iterations per grid configuration.",
    )
    parser.add_argument(
        "--grid-batch-size",
        action="append",
        type=int,
        help="Batch size to evaluate (repeatable).",
    )
    parser.add_argument(
        "--grid-preset",
        action="append",
        help="Operator preset to evaluate (repeatable).",
    )
    parser.add_argument(
        "--bayes-trials",
        type=int,
        help="Number of Bayesian optimisation trials per scenario.",
    )
    parser.add_argument(
        "--bayes-iters",
        type=int,
        help="Iterations per Bayesian optimisation trial.",
    )
    parser.add_argument(
        "--ils-runs",
        type=int,
        help="Number of Iterated Local Search restarts per scenario.",
    )
    parser.add_argument(
        "--ils-iters",
        type=int,
        help="Iterated Local Search iterations per restart.",
    )
    parser.add_argument(
        "--ils-base-seed",
        type=int,
        help="Base seed for Iterated Local Search runs (incremented per run).",
    )
    parser.add_argument(
        "--tabu-runs",
        type=int,
        help="Number of Tabu Search restarts per scenario.",
    )
    parser.add_argument(
        "--tabu-iters",
        type=int,
        help="Tabu Search iterations per restart.",
    )
    parser.add_argument(
        "--tabu-base-seed",
        type=int,
        help="Base seed for Tabu Search runs (incremented per run).",
    )
    parser.add_argument(
        "--summary-label",
        default="current",
        help="Report label used when generating summary tables (default: current).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print commands before executing them.",
    )
    return parser.parse_args(argv)


def ensure_clean_log(log_path: Path, append: bool) -> None:
    if append:
        return
    if log_path.exists():
        log_path.unlink()
    sqlite_path = log_path.with_suffix(".sqlite")
    if sqlite_path.exists():
        sqlite_path.unlink()
    steps_dir = log_path.parent / "steps"
    if steps_dir.exists():
        shutil.rmtree(steps_dir)


def _resolve_heuristic_scenarios(
    scenario_args: Sequence[Path] | None,
    bundle_specs: Sequence[str] | None,
) -> tuple[list[Path], dict[Path, dict[str, str]]]:
    try:
        scenarios, bundle_map = _collect_tuning_scenarios(scenario_args or [], bundle_specs or [])
    except typer.BadParameter as exc:  # pragma: no cover - delegated CLI validation
        raise RuntimeError(f"Failed to resolve scenarios for heuristics: {exc}") from exc
    ordered: list[Path] = []
    seen: set[Path] = set()
    for scenario_path in scenarios:
        resolved = scenario_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(scenario_path)
    return ordered, bundle_map


def _scenario_display_name(scenario_path: Path, sc: Any) -> str:
    return (
        getattr(sc, "name", None)
        or scenario_path.parent.name
        or scenario_path.stem
    )


def _build_context_payload(
    *,
    algorithm: str,
    scenario_path: Path,
    scenario_label: str,
    bundle_meta: dict[str, str] | None,
    tier_label: str | None,
    budget: dict[str, Any],
    progress: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "source": f"benchmark.{algorithm}",
        "scenario_path": str(scenario_path),
        "scenario_label": scenario_label,
    }
    if bundle_meta:
        context["bundle"] = bundle_meta.get("bundle")
        context["bundle_member"] = bundle_meta.get("bundle_member", scenario_label)
    if tier_label:
        context["tier"] = tier_label
    tuner_meta = {
        "algorithm": algorithm,
        "budget": budget,
        "progress": progress,
    }
    if config:
        tuner_meta["config"] = config
    if bundle_meta:
        tuner_meta["bundle"] = bundle_meta.get("bundle")
        tuner_meta["bundle_member"] = bundle_meta.get("bundle_member", scenario_label)
    context["tuner_meta"] = tuner_meta
    return context


def _run_ils_benchmarks(
    scenario_files: Sequence[Path],
    bundle_map: dict[Path, dict[str, str]],
    telemetry_log: Path,
    *,
    runs: int,
    iters: int,
    base_seed: int,
    tier_label: str | None,
    extra_kwargs: dict[str, Any],
    verbose: bool,
) -> None:
    if runs <= 0 or iters <= 0:
        return
    seed_counter = base_seed
    for scenario_index, scenario_path in enumerate(scenario_files):
        sc = load_scenario(str(scenario_path))
        scenario_label = _scenario_display_name(scenario_path, sc)
        bundle_meta = bundle_map.get(scenario_path.resolve())
        if verbose:
            meta_str = (
                f"bundle={bundle_meta['bundle']}, member={bundle_meta.get('bundle_member')}"
                if bundle_meta
                else "standalone"
            )
            print(
                f"[ILS] {scenario_label} ({meta_str}) — runs={runs}, iters={iters}, tier={tier_label or 'n/a'}"
            )
        for run_idx in range(runs):
            pb = Problem.from_scenario(sc)
            run_seed = seed_counter
            seed_counter += 1
            budget_payload = {
                "runs_total": runs,
                "iters_per_run": iters,
                "tier": tier_label,
            }
            progress_payload = {
                "run_index": run_idx + 1,
                "total_runs": runs,
            }
            config_payload = {
                key: value for key, value in extra_kwargs.items() if key in {
                    "perturbation_strength",
                    "stall_limit",
                    "hybrid_use_mip",
                    "hybrid_mip_time_limit",
                    "batch_size",
                    "max_workers",
                }
            }
            telemetry_context = _build_context_payload(
                algorithm="ils",
                scenario_path=scenario_path,
                scenario_label=scenario_label,
                bundle_meta=bundle_meta,
                tier_label=tier_label,
                budget=budget_payload,
                progress=progress_payload,
                config=config_payload or None,
            )
            telemetry_context["run_seed"] = run_seed
            solve_ils(
                pb,
                iters=iters,
                seed=run_seed,
                telemetry_log=telemetry_log,
                telemetry_context=telemetry_context,
                **extra_kwargs,
            )


def _run_tabu_benchmarks(
    scenario_files: Sequence[Path],
    bundle_map: dict[Path, dict[str, str]],
    telemetry_log: Path,
    *,
    runs: int,
    iters: int,
    base_seed: int,
    tier_label: str | None,
    extra_kwargs: dict[str, Any],
    verbose: bool,
) -> None:
    if runs <= 0 or iters <= 0:
        return
    seed_counter = base_seed
    for scenario_index, scenario_path in enumerate(scenario_files):
        sc = load_scenario(str(scenario_path))
        scenario_label = _scenario_display_name(scenario_path, sc)
        bundle_meta = bundle_map.get(scenario_path.resolve())
        if verbose:
            meta_str = (
                f"bundle={bundle_meta['bundle']}, member={bundle_meta.get('bundle_member')}"
                if bundle_meta
                else "standalone"
            )
            print(
                f"[Tabu] {scenario_label} ({meta_str}) — runs={runs}, iters={iters}, tier={tier_label or 'n/a'}"
            )
        for run_idx in range(runs):
            pb = Problem.from_scenario(sc)
            run_seed = seed_counter
            seed_counter += 1
            budget_payload = {
                "runs_total": runs,
                "iters_per_run": iters,
                "tier": tier_label,
            }
            progress_payload = {
                "run_index": run_idx + 1,
                "total_runs": runs,
            }
            config_payload = {
                key: value for key, value in extra_kwargs.items() if key in {
                    "tabu_tenure",
                    "stall_limit",
                    "batch_size",
                    "max_workers",
                }
            }
            telemetry_context = _build_context_payload(
                algorithm="tabu",
                scenario_path=scenario_path,
                scenario_label=scenario_label,
                bundle_meta=bundle_meta,
                tier_label=tier_label,
                budget=budget_payload,
                progress=progress_payload,
                config=config_payload or None,
            )
            telemetry_context["run_seed"] = run_seed
            solve_tabu(
                pb,
                iters=iters,
                seed=run_seed,
                telemetry_log=telemetry_log,
                telemetry_context=telemetry_context,
                **extra_kwargs,
            )


def run_tuner_commands(
    *,
    bundles: list[str],
    scenarios: list[Path],
    telemetry_log: Path,
    tuners: list[str],
    random_runs: int,
    random_iters: int,
    grid_iters: int,
    grid_batch_sizes: list[int],
    grid_presets: list[str],
    bayes_trials: int,
    bayes_iters: int,
    ils_config: dict[str, Any] | None,
    tabu_config: dict[str, Any] | None,
    heuristic_scenarios: list[Path] | None,
    heuristic_bundle_map: dict[Path, dict[str, str]] | None,
    verbose: bool,
    tier_label: str | None = None,
) -> None:
    bundle_arguments = _bundle_args(bundles) if bundles else []
    scenario_arguments = _scenario_args(scenarios) if scenarios else []
    target_arguments = bundle_arguments + scenario_arguments

    if not target_arguments and not (heuristic_scenarios and tuners):
        raise ValueError("No bundles or scenarios specified for tuning.")

    if target_arguments and any(
        name in tuners for name in ("random", "grid", "bayes")
    ):
        if "random" in tuners:
            cmd = (
                CLI_ENTRY_POINT
                + ["tune-random"]
                + target_arguments
                + [
                    "--telemetry-log",
                    str(telemetry_log),
                    "--runs",
                    str(random_runs),
                    "--iters",
                    str(random_iters),
                ]
            )
            if tier_label:
                cmd.extend(["--tier-label", tier_label])
            _run(cmd, verbose=verbose)

        if "grid" in tuners:
            cmd = (
                CLI_ENTRY_POINT
                + ["tune-grid"]
                + target_arguments
                + [
                    "--telemetry-log",
                    str(telemetry_log),
                    "--iters",
                    str(grid_iters),
                ]
            )
            for batch_size in grid_batch_sizes:
                cmd.extend(["--batch-size", str(batch_size)])
            for preset in grid_presets:
                cmd.extend(["--preset", preset])
            if tier_label:
                cmd.extend(["--tier-label", tier_label])
            _run(cmd, verbose=verbose)

        if "bayes" in tuners:
            cmd = (
                CLI_ENTRY_POINT
                + ["tune-bayes"]
                + target_arguments
                + [
                    "--telemetry-log",
                    str(telemetry_log),
                    "--trials",
                    str(bayes_trials),
                    "--iters",
                    str(bayes_iters),
                ]
            )
            if tier_label:
                cmd.extend(["--tier-label", tier_label])
            _run(cmd, verbose=verbose)

    heuristics_requested = any(name in tuners for name in ("ils", "tabu"))
    scenario_files = heuristic_scenarios or []
    bundle_map = heuristic_bundle_map or {}

    if heuristics_requested and not scenario_files:
        raise ValueError(
            "Heuristic tuners (ILS/Tabu) require scenarios resolved from --bundle or --scenario."
        )

    telemetry_path = telemetry_log.resolve() if heuristics_requested else telemetry_log

    if "ils" in tuners:
        config = ils_config or {}
        runs = int(config.get("runs", DEFAULT_ILS_RUNS))
        iters = int(config.get("iters", DEFAULT_ILS_ITERS))
        seed = int(config.get("seed", DEFAULT_ILS_SEED))
        extra_kwargs = dict(config.get("extra_kwargs", {}))
        _run_ils_benchmarks(
            scenario_files,
            bundle_map,
            telemetry_path,
            runs=max(0, runs),
            iters=max(0, iters),
            base_seed=seed,
            tier_label=tier_label,
            extra_kwargs=extra_kwargs,
            verbose=verbose,
        )

    if "tabu" in tuners:
        config = tabu_config or {}
        runs = int(config.get("runs", DEFAULT_TABU_RUNS))
        iters = int(config.get("iters", DEFAULT_TABU_ITERS))
        seed = int(config.get("seed", DEFAULT_TABU_SEED))
        extra_kwargs = dict(config.get("extra_kwargs", {}))
        _run_tabu_benchmarks(
            scenario_files,
            bundle_map,
            telemetry_path,
            runs=max(0, runs),
            iters=max(0, iters),
            base_seed=seed,
            tier_label=tier_label,
            extra_kwargs=extra_kwargs,
            verbose=verbose,
        )


def generate_reports(
    *,
    telemetry_log: Path,
    report_dir: Path,
    summary_label: str,
    verbose: bool,
) -> tuple[Path, Path, Path]:
    sqlite_path = telemetry_log.with_suffix(".sqlite")
    report_csv = report_dir / "tuner_report.csv"
    report_md = report_dir / "tuner_report.md"
    summary_csv = report_dir / "tuner_summary.csv"
    summary_md = report_dir / "tuner_summary.md"

    cmd = CLI_ENTRY_POINT + [
        "telemetry",
        "report",
        str(sqlite_path),
        "--out-csv",
        str(report_csv),
        "--out-markdown",
        str(report_md),
    ]
    _run(cmd, verbose=verbose)

    analyze_cmd = ANALYZE_SCRIPT + [
        "--report",
        f"{summary_label}={report_csv}",
        "--out-summary-csv",
        str(summary_csv),
        "--out-summary-markdown",
        str(summary_md),
    ]
    _run(analyze_cmd, verbose=verbose)
    return report_csv, summary_csv, summary_md


def _infer_algorithm(source: str | None, solver: str | None) -> str:
    if source:
        if source.startswith("cli.tune-random"):
            return "random"
        if source.startswith("cli.tune-grid"):
            return "grid"
        if source.startswith("cli.tune-bayes"):
            return "bayes"
    if solver:
        solver_lower = solver.lower()
        if solver_lower in {"sa", "ils", "tabu"}:
            return solver_lower
    return "unknown"


def _render_markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "*(no data)*"
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        cells: list[str] = []
        for col in headers:
            value = row[col]
            if value is None or (isinstance(value, float) and pd.isna(value)):
                cells.append("")
            elif isinstance(value, float):
                cells.append(f"{value:.3f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _sanitize_bundle_name(name: str) -> str:
    return name.replace("/", "_").replace(":", "_").replace(" ", "_")


def generate_comparisons(sqlite_path: Path, out_dir: Path) -> dict[str, object]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            runs.run_id,
            runs.solver,
            runs.scenario,
            runs.duration_seconds,
            runs.context_json,
            runs.tuner_meta_json,
            metrics.value AS objective
        FROM runs
        JOIN run_metrics AS metrics
            ON metrics.run_id = runs.run_id
           AND metrics.name = 'objective'
        """
    ).fetchall()
    conn.close()

    scenario_data: dict[str, dict[str, dict[str, list[float]]]] = {}
    scenario_display: dict[str, str] = {}
    scenario_bundle: dict[str, str] = {}
    scenario_mip: dict[str, float] = {}

    for row in rows:
        context = json.loads(row["context_json"] or "{}")
        tuner_meta = json.loads(row["tuner_meta_json"] or "{}")
        algorithm = tuner_meta.get("algorithm") or context.get("algorithm") or _infer_algorithm(
            context.get("source"), row["solver"]
        )
        bundle = context.get("bundle")
        bundle_member = context.get("bundle_member")
        scenario_name = row["scenario"] or bundle_member or "unknown"
        if bundle:
            scenario_key = f"{bundle}:{bundle_member or scenario_name}"
            display_name = scenario_key
            bundle_name = bundle
        else:
            scenario_key = scenario_name
            display_name = scenario_name
            bundle_name = "standalone"
        scenario_display[scenario_key] = display_name
        scenario_bundle.setdefault(scenario_key, bundle_name)

        objective_value = float(row["objective"]) if row["objective"] is not None else None
        if algorithm == "mip":
            if objective_value is not None:
                previous = scenario_mip.get(scenario_key)
                scenario_mip[scenario_key] = (
                    max(previous, objective_value) if previous is not None else objective_value
                )
            continue

        data = scenario_data.setdefault(scenario_key, {}).setdefault(
            algorithm, {"objectives": [], "runtimes": []}
        )
        if objective_value is not None:
            data["objectives"].append(objective_value)
        duration = row["duration_seconds"]
        if duration is not None:
            data["runtimes"].append(float(duration))

    def compute_metrics(selected_keys: set[str] | None):
        summary_template = lambda: {
            "wins": 0,
            "scenario_participation": 0,
            "best_values": [],
            "mean_values": [],
            "runtime_values": [],
            "delta_values": [],
        }
        algorithm_summary: dict[str, dict[str, object]] = defaultdict(summary_template)
        comparison_rows: list[dict[str, object]] = []
        difficulty_rows: list[dict[str, object]] = []
        scenarios_considered: list[str] = []

        for scenario_key, alg_stats in scenario_data.items():
            if selected_keys is not None and scenario_key not in selected_keys:
                continue
            if not alg_stats:
                continue
            scenario_name = scenario_display.get(scenario_key, scenario_key)
            bundle_name = scenario_bundle.get(scenario_key, "standalone")
            objective_entries: list[tuple[str, float, float, float | None]] = []
            for algorithm, stats in alg_stats.items():
                objectives = stats["objectives"]
                if not objectives:
                    continue
                best_obj = max(objectives)
                mean_obj = fmean(objectives)
                runtimes = stats["runtimes"]
                avg_runtime = fmean(runtimes) if runtimes else None
                objective_entries.append((algorithm, best_obj, mean_obj, avg_runtime))
            if not objective_entries:
                continue
            scenarios_considered.append(scenario_key)
            objective_entries.sort(key=lambda item: item[1], reverse=True)
            overall_best = objective_entries[0][1]
            second_best_delta = (
                objective_entries[0][1] - objective_entries[1][1]
                if len(objective_entries) > 1
                else None
            )
            for algorithm, best_obj, mean_obj, avg_runtime in objective_entries:
                delta_vs_best = best_obj - overall_best
                comparison_rows.append(
                    {
                        "scenario": scenario_name,
                        "bundle": bundle_name,
                        "algorithm": algorithm,
                        "best_objective": best_obj,
                        "mean_objective": mean_obj,
                        "mean_runtime": avg_runtime,
                        "delta_vs_best": delta_vs_best,
                    }
                )
                summary = algorithm_summary[algorithm]
                summary["scenario_participation"] += 1
                summary["best_values"].append(best_obj)
                summary["mean_values"].append(mean_obj)
                summary["delta_values"].append(delta_vs_best)
                if avg_runtime is not None:
                    summary["runtime_values"].append(avg_runtime)
                if abs(delta_vs_best) < 1e-9:
                    summary["wins"] += 1

            mip_obj = scenario_mip.get(scenario_key)
            difficulty_rows.append(
                {
                    "scenario": scenario_name,
                    "bundle": bundle_name,
                    "best_algorithm": objective_entries[0][0],
                    "best_objective": objective_entries[0][1],
                    "second_best_delta": second_best_delta,
                    "mip_objective": mip_obj,
                    "mip_gap": (mip_obj - objective_entries[0][1]) if mip_obj is not None else None,
                    "algorithms_evaluated": len(objective_entries),
                }
            )

        comparison_df = pd.DataFrame(comparison_rows)
        if not comparison_df.empty:
            comparison_df.sort_values(
                ["bundle", "scenario", "algorithm"], ascending=[True, True, True], inplace=True
            )

        scenario_count = len(set(scenarios_considered))
        leaderboard_rows: list[dict[str, object]] = []
        for algorithm, stats in algorithm_summary.items():
            if stats["scenario_participation"] == 0 or scenario_count == 0:
                continue
            wins = stats["wins"]
            leaderboard_rows.append(
                {
                    "algorithm": algorithm,
                    "wins": wins,
                    "scenarios": scenario_count,
                    "win_rate": wins / scenario_count if scenario_count else 0.0,
                    "avg_best_objective": fmean(stats["best_values"]) if stats["best_values"] else None,
                    "avg_mean_objective": fmean(stats["mean_values"]) if stats["mean_values"] else None,
                    "avg_runtime": fmean(stats["runtime_values"]) if stats["runtime_values"] else None,
                    "avg_delta_vs_best": fmean(stats["delta_values"]) if stats["delta_values"] else None,
                }
            )
        leaderboard_df = pd.DataFrame(leaderboard_rows).sort_values(
            ["win_rate", "algorithm"], ascending=[False, True]
        )

        difficulty_df = pd.DataFrame(difficulty_rows).sort_values(
            ["bundle", "scenario"], ascending=[True, True]
        )
        return comparison_df, leaderboard_df, difficulty_df

    comparison_df, leaderboard_df, difficulty_df = compute_metrics(None)

    comparison_csv = out_dir / "tuner_comparison.csv"
    comparison_md = out_dir / "tuner_comparison.md"
    leaderboard_csv = out_dir / "tuner_leaderboard.csv"
    leaderboard_md = out_dir / "tuner_leaderboard.md"
    difficulty_csv = out_dir / "tuner_difficulty.csv"
    difficulty_md = out_dir / "tuner_difficulty.md"

    comparison_df.to_csv(comparison_csv, index=False)
    comparison_md.write_text(_render_markdown_table(comparison_df), encoding="utf-8")
    leaderboard_df.to_csv(leaderboard_csv, index=False)
    leaderboard_md.write_text(_render_markdown_table(leaderboard_df), encoding="utf-8")
    difficulty_df.to_csv(difficulty_csv, index=False)
    difficulty_md.write_text(_render_markdown_table(difficulty_df), encoding="utf-8")

    bundle_outputs: dict[str, dict[str, Path]] = {}
    for bundle_name in sorted(set(scenario_bundle.values())):
        selected_keys = {key for key, value in scenario_bundle.items() if value == bundle_name}
        bundle_comp, bundle_leader, bundle_diff = compute_metrics(selected_keys)
        if bundle_comp.empty:
            continue
        sanitized = _sanitize_bundle_name(bundle_name)
        comp_csv = out_dir / f"tuner_comparison_{sanitized}.csv"
        comp_md = out_dir / f"tuner_comparison_{sanitized}.md"
        leader_csv = out_dir / f"tuner_leaderboard_{sanitized}.csv"
        leader_md = out_dir / f"tuner_leaderboard_{sanitized}.md"
        diff_csv = out_dir / f"tuner_difficulty_{sanitized}.csv"
        diff_md = out_dir / f"tuner_difficulty_{sanitized}.md"
        bundle_comp.to_csv(comp_csv, index=False)
        comp_md.write_text(_render_markdown_table(bundle_comp), encoding="utf-8")
        bundle_leader.to_csv(leader_csv, index=False)
        leader_md.write_text(_render_markdown_table(bundle_leader), encoding="utf-8")
        bundle_diff.to_csv(diff_csv, index=False)
        diff_md.write_text(_render_markdown_table(bundle_diff), encoding="utf-8")
        bundle_outputs[bundle_name] = {
            "comparison_csv": comp_csv,
            "comparison_md": comp_md,
            "leaderboard_csv": leader_csv,
            "leaderboard_md": leader_md,
            "difficulty_csv": diff_csv,
            "difficulty_md": diff_md,
        }

    return {
        "comparison_csv": comparison_csv,
        "comparison_md": comparison_md,
        "leaderboard_csv": leaderboard_csv,
        "leaderboard_md": leaderboard_md,
        "difficulty_csv": difficulty_csv,
        "difficulty_md": difficulty_md,
        "per_bundle": bundle_outputs,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    plan_cfg: dict[str, object] | None = None
    if args.plan:
        plan_cfg = BENCHMARK_PLANS.get(args.plan)
        if plan_cfg is None:
            raise ValueError(f"Unknown plan '{args.plan}'. Available: {', '.join(BENCHMARK_PLANS)}")

    tuners = args.tuner or (plan_cfg.get("tuners") if plan_cfg else None) or DEFAULT_TUNERS

    requested_tiers = list(args.tier or [])
    if not requested_tiers and plan_cfg and plan_cfg.get("tiers"):
        requested_tiers = list(plan_cfg["tiers"])  # type: ignore[index]
    if not requested_tiers:
        requested_tiers = list(DEFAULT_TIERS)
    tiers: list[str] = []
    for tier in requested_tiers:
        if tier not in TIER_BUDGETS:
            raise ValueError(
                f"Unknown tier '{tier}'. Valid options: {', '.join(sorted(TIER_BUDGETS))}."
            )
        if tier not in tiers:
            tiers.append(tier)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    telemetry_log = args.telemetry_log or (out_dir / "telemetry" / "runs.jsonl")
    telemetry_log.parent.mkdir(parents=True, exist_ok=True)
    ensure_clean_log(telemetry_log, append=args.append)

    bundles = list(args.bundle or [])
    if plan_cfg and not bundles:
        bundles = list(plan_cfg.get("bundles", []))  # type: ignore[arg-type]
    if not bundles:
        bundles = ["baseline"]

    scenario_paths = list(args.scenario or [])
    if plan_cfg and not scenario_paths and plan_cfg.get("scenarios"):
        scenario_paths = [Path(p) for p in plan_cfg["scenarios"]]  # type: ignore[arg-type]

    plan_budgets = (plan_cfg.get("budgets") if plan_cfg else {}) or {}

    heuristics_needed = any(name in tuners for name in ("ils", "tabu"))
    heuristic_scenarios: list[Path] = []
    heuristic_bundle_map: dict[Path, dict[str, str]] = {}
    if heuristics_needed:
        heuristic_scenarios, heuristic_bundle_map = _resolve_heuristic_scenarios(
            scenario_paths,
            bundles,
        )

    for tier in tiers:
        tier_config = deepcopy(TIER_BUDGETS[tier])
        if plan_budgets:
            all_overrides = plan_budgets.get("all")  # type: ignore[index]
            if all_overrides:
                for tuner_name, tuner_cfg in all_overrides.items():  # type: ignore[assignment]
                    if tuner_name in tier_config:
                        tier_config[tuner_name].update(deepcopy(tuner_cfg))  # type: ignore[index]
            tier_overrides = plan_budgets.get(tier)  # type: ignore[index]
            if tier_overrides:
                for tuner_name, tuner_cfg in tier_overrides.items():  # type: ignore[assignment]
                    if tuner_name in tier_config:
                        tier_config[tuner_name].update(deepcopy(tuner_cfg))  # type: ignore[index]

        random_cfg = dict(tier_config.get("random", {}))
        grid_cfg = dict(tier_config.get("grid", {}))
        bayes_cfg = dict(tier_config.get("bayes", {}))

        if args.random_runs is not None:
            random_cfg["runs"] = args.random_runs
        if args.random_iters is not None:
            random_cfg["iters"] = args.random_iters
        if args.grid_iters is not None:
            grid_cfg["iters"] = args.grid_iters
        if args.grid_batch_size:
            grid_cfg["batch_sizes"] = list(args.grid_batch_size)
        if args.grid_preset:
            grid_cfg["presets"] = list(args.grid_preset)
        if args.bayes_trials is not None:
            bayes_cfg["trials"] = args.bayes_trials
        if args.bayes_iters is not None:
            bayes_cfg["iters"] = args.bayes_iters

        random_runs = int(random_cfg.get("runs", DEFAULT_RANDOM_RUNS))
        random_iters = int(random_cfg.get("iters", DEFAULT_RANDOM_ITERS))
        grid_iters = int(grid_cfg.get("iters", DEFAULT_GRID_ITERS))
        grid_batch_sizes = list(grid_cfg.get("batch_sizes") or DEFAULT_GRID_BATCH_SIZES)
        grid_presets = list(grid_cfg.get("presets") or DEFAULT_GRID_PRESETS)
        bayes_trials = int(bayes_cfg.get("trials", DEFAULT_BAYES_TRIALS))
        bayes_iters = int(bayes_cfg.get("iters", DEFAULT_BAYES_ITERS))

        ils_config_payload: dict[str, Any] | None = None
        ils_runs_display: int | None = None
        ils_iters_display: int | None = None
        if "ils" in tuners:
            ils_cfg = dict(tier_config.get("ils", {}))
            if args.ils_runs is not None:
                ils_cfg["runs"] = args.ils_runs
            if args.ils_iters is not None:
                ils_cfg["iters"] = args.ils_iters
            if args.ils_base_seed is not None:
                ils_cfg["seed"] = args.ils_base_seed
            ils_runs_value = int(ils_cfg.pop("runs", DEFAULT_ILS_RUNS))
            ils_iters_value = int(ils_cfg.pop("iters", DEFAULT_ILS_ITERS))
            ils_seed_value = int(ils_cfg.pop("seed", DEFAULT_ILS_SEED))
            ils_config_payload = {
                "runs": ils_runs_value,
                "iters": ils_iters_value,
                "seed": ils_seed_value,
                "extra_kwargs": ils_cfg,
            }
            ils_runs_display = ils_runs_value
            ils_iters_display = ils_iters_value

        tabu_config_payload: dict[str, Any] | None = None
        tabu_runs_display: int | None = None
        tabu_iters_display: int | None = None
        if "tabu" in tuners:
            tabu_cfg = dict(tier_config.get("tabu", {}))
            if args.tabu_runs is not None:
                tabu_cfg["runs"] = args.tabu_runs
            if args.tabu_iters is not None:
                tabu_cfg["iters"] = args.tabu_iters
            if args.tabu_base_seed is not None:
                tabu_cfg["seed"] = args.tabu_base_seed
            tabu_runs_value = int(tabu_cfg.pop("runs", DEFAULT_TABU_RUNS))
            tabu_iters_value = int(tabu_cfg.pop("iters", DEFAULT_TABU_ITERS))
            tabu_seed_value = int(tabu_cfg.pop("seed", DEFAULT_TABU_SEED))
            tabu_config_payload = {
                "runs": tabu_runs_value,
                "iters": tabu_iters_value,
                "seed": tabu_seed_value,
                "extra_kwargs": tabu_cfg,
            }
            tabu_runs_display = tabu_runs_value
            tabu_iters_display = tabu_iters_value

        if args.verbose:
            message = (
                f"[tier:{tier}] random(runs={random_runs}, iters={random_iters}) "
                f"grid(iters={grid_iters}, batches={grid_batch_sizes}, presets={grid_presets}) "
                f"bayes(trials={bayes_trials}, iters={bayes_iters})"
            )
            if ils_runs_display is not None and ils_iters_display is not None:
                message += f" ils(runs={ils_runs_display}, iters={ils_iters_display})"
            if tabu_runs_display is not None and tabu_iters_display is not None:
                message += f" tabu(runs={tabu_runs_display}, iters={tabu_iters_display})"
            print(message)

        run_tuner_commands(
            bundles=bundles,
            scenarios=scenario_paths,
            telemetry_log=telemetry_log,
            tuners=tuners,
            random_runs=random_runs,
            random_iters=random_iters,
            grid_iters=grid_iters,
            grid_batch_sizes=[int(x) for x in grid_batch_sizes],
            grid_presets=[str(x) for x in grid_presets],
            bayes_trials=bayes_trials,
            bayes_iters=bayes_iters,
            ils_config=ils_config_payload,
            tabu_config=tabu_config_payload,
            heuristic_scenarios=heuristic_scenarios if heuristics_needed else None,
            heuristic_bundle_map=heuristic_bundle_map if heuristics_needed else None,
            verbose=args.verbose,
            tier_label=tier,
        )

    report_csv, summary_csv, summary_md = generate_reports(
        telemetry_log=telemetry_log,
        report_dir=out_dir,
        summary_label=args.summary_label,
        verbose=args.verbose,
    )

    comparison_artifacts = generate_comparisons(
        telemetry_log.with_suffix(".sqlite"), out_dir
    )

    if args.verbose:
        print("Telemetry log:", telemetry_log)
        print("Report CSV:", report_csv)
        print("Summary CSV:", summary_csv)
        print("Summary Markdown:", summary_md)
        print("Comparison CSV:", comparison_artifacts["comparison_csv"])
        print("Comparison Markdown:", comparison_artifacts["comparison_md"])
        print("Leaderboard CSV:", comparison_artifacts["leaderboard_csv"])
        print("Leaderboard Markdown:", comparison_artifacts["leaderboard_md"])
        print("Difficulty CSV:", comparison_artifacts["difficulty_csv"])
        print("Difficulty Markdown:", comparison_artifacts["difficulty_md"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
