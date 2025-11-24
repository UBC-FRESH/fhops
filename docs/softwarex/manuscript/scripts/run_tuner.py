#!/usr/bin/env python3
"""Run condensed tuning studies for SoftwareX manuscript assets."""

from __future__ import annotations

import argparse
import subprocess
import sys
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="FHOPS repository root.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory to store tuning telemetry and reports "
        "(defaults to docs/softwarex/assets/data/tuning).",
    )
    parser.add_argument(
        "--tier",
        default="short",
        help="Budget tier passed to run_tuning_benchmarks (default: short).",
    )
    return parser.parse_args()


def ensure_path(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = (
        args.out_dir
        if args.out_dir is not None
        else repo_root / "docs" / "softwarex" / "assets" / "data" / "tuning"
    ).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    datasets_dir = repo_root / "docs" / "softwarex" / "assets" / "data" / "datasets"
    synthetic_scenario = ensure_path(datasets_dir / "synthetic_small" / "scenario.yaml")

    scenarios = [
        ensure_path(repo_root / "examples" / "minitoy" / "scenario.yaml"),
        ensure_path(repo_root / "examples" / "med42" / "scenario.yaml"),
        synthetic_scenario,
    ]

    fast_mode = os.environ.get("FHOPS_ASSETS_FAST", "0") == "1"
    random_iters = "200"
    grid_iters = "200"
    bayes_trials = "15"
    bayes_iters = "200"
    ils_iters = "220"
    tabu_iters = "1500"

    if fast_mode:
        random_iters = "120"
        grid_iters = "120"
        bayes_trials = "8"
        bayes_iters = "120"
        ils_iters = "160"
        tabu_iters = "900"
        print("[tuning] FAST mode enabled for tuner budgets", flush=True)

    cmd: list[str] = [
        sys.executable,
        "scripts/run_tuning_benchmarks.py",
        "--tier",
        args.tier,
        "--tuner",
        "random",
        "--tuner",
        "grid",
        "--tuner",
        "bayes",
        "--tuner",
        "ils",
        "--tuner",
        "tabu",
        "--out-dir",
        str(out_dir),
        "--summary-label",
        "softwarex",
        "--random-runs",
        "2",
        "--random-iters",
        random_iters,
        "--grid-iters",
        grid_iters,
        "--grid-batch-size",
        "1",
        "--grid-batch-size",
        "2",
        "--grid-preset",
        "balanced",
        "--grid-preset",
        "explore",
        "--bayes-trials",
        bayes_trials,
        "--bayes-iters",
        bayes_iters,
        "--ils-runs",
        "1",
        "--ils-iters",
        ils_iters,
        "--tabu-runs",
        "1",
        "--tabu-iters",
        tabu_iters,
    ]

    for scenario_path in scenarios:
        cmd.extend(["--scenario", str(scenario_path)])

    print(f"[tuning] Running condensed studies into {out_dir}")
    subprocess.run(cmd, cwd=repo_root, check=True)
    print("[tuning] Complete. Reports available under", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
