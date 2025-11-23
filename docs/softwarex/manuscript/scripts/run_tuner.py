#!/usr/bin/env python3
"""Run condensed tuning studies for SoftwareX manuscript assets."""

from __future__ import annotations

import argparse
import subprocess
import sys
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
        "200",
        "--grid-iters",
        "200",
        "--grid-batch-size",
        "1",
        "--grid-batch-size",
        "2",
        "--grid-preset",
        "balanced",
        "--grid-preset",
        "explore",
        "--bayes-trials",
        "15",
        "--bayes-iters",
        "200",
        "--ils-runs",
        "1",
        "--ils-iters",
        "220",
        "--tabu-runs",
        "1",
        "--tabu-iters",
        "1500",
    ]

    for scenario_path in scenarios:
        cmd.extend(["--scenario", str(scenario_path)])

    print(f"[tuning] Running condensed studies into {out_dir}")
    subprocess.run(cmd, cwd=repo_root, check=True)
    print("[tuning] Complete. Reports available under", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
