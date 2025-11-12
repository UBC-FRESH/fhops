#!/usr/bin/env python
"""Run multiple tuning strategies over scenario bundles and aggregate telemetry."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


CLI_ENTRY_POINT = [sys.executable, "-m", "fhops.cli.main"]
ANALYZE_SCRIPT = [sys.executable, "scripts/analyze_tuner_reports.py"]


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
        default=["baseline"],
        help="Scenario bundle alias or path (repeatable). Defaults to 'baseline'.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        type=Path,
        help="Explicit scenario YAML path (repeatable).",
    )
    parser.add_argument(
        "--tuner",
        action="append",
        choices=["random", "grid", "bayes"],
        help="Subset of tuners to run (default: all).",
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
        default=3,
        help="Number of random tuner runs per scenario.",
    )
    parser.add_argument(
        "--random-iters",
        type=int,
        default=250,
        help="Simulated annealing iterations per random tuner run.",
    )
    parser.add_argument(
        "--grid-iters",
        type=int,
        default=250,
        help="Simulated annealing iterations per grid configuration.",
    )
    parser.add_argument(
        "--grid-batch-size",
        action="append",
        type=int,
        help="Batch size to evaluate (repeatable, default: 1 and 2).",
    )
    parser.add_argument(
        "--grid-preset",
        action="append",
        help="Operator preset to evaluate (repeatable, default: balanced and explore).",
    )
    parser.add_argument(
        "--bayes-trials",
        type=int,
        default=20,
        help="Number of Bayesian optimisation trials per scenario.",
    )
    parser.add_argument(
        "--bayes-iters",
        type=int,
        default=250,
        help="Iterations per Bayesian optimisation trial.",
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
    verbose: bool,
) -> None:
    bundle_arguments = _bundle_args(bundles) if bundles else []
    scenario_arguments = _scenario_args(scenarios) if scenarios else []
    target_arguments = bundle_arguments + scenario_arguments
    if not target_arguments:
        raise ValueError("No bundles or scenarios specified for tuning.")

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
        _run(cmd, verbose=verbose)


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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    tuners = args.tuner or ["random", "grid", "bayes"]
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    telemetry_log = args.telemetry_log or (out_dir / "telemetry" / "runs.jsonl")
    telemetry_log.parent.mkdir(parents=True, exist_ok=True)
    ensure_clean_log(telemetry_log, append=args.append)

    grid_batch_sizes = args.grid_batch_size or [1, 2]
    grid_presets = args.grid_preset or ["balanced", "explore"]

    run_tuner_commands(
        bundles=args.bundle or [],
        scenarios=args.scenario or [],
        telemetry_log=telemetry_log,
        tuners=tuners,
        random_runs=args.random_runs,
        random_iters=args.random_iters,
        grid_iters=args.grid_iters,
        grid_batch_sizes=grid_batch_sizes,
        grid_presets=grid_presets,
        bayes_trials=args.bayes_trials,
        bayes_iters=args.bayes_iters,
        verbose=args.verbose,
    )

    report_csv, summary_csv, summary_md = generate_reports(
        telemetry_log=telemetry_log,
        report_dir=out_dir,
        summary_label=args.summary_label,
        verbose=args.verbose,
    )

    if args.verbose:
        print("Telemetry log:", telemetry_log)
        print("Report CSV:", report_csv)
        print("Summary CSV:", summary_csv)
        print("Summary Markdown:", summary_md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
