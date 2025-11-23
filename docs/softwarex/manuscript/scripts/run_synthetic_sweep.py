#!/usr/bin/env python3
"""Generate synthetic tier benchmarks (small/medium/large) for scaling plots."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


@dataclass
class TierSpec:
    name: str
    seed: int


TIERS = [
    TierSpec("small", 101),
    TierSpec("medium", 202),
    TierSpec("large", 303),
]


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
        help="Scaling asset directory (defaults to docs/softwarex/assets/data/scaling).",
    )
    return parser.parse_args()


def run_cmd(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def synth_bundle(repo_root: Path, tier: TierSpec, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python",
        "-m",
        "fhops.cli.main",
        "synth",
        "generate",
        str(dest),
        "--tier",
        tier.name,
        "--seed",
        str(tier.seed),
        "--overwrite",
    ]
    run_cmd(cmd, repo_root)
    scenario = dest / "scenario.yaml"
    if not scenario.exists():
        raise FileNotFoundError(scenario)
    return scenario


def bench_scenario(repo_root: Path, scenario: Path, out_dir: Path) -> Path:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python",
        "-m",
        "fhops.cli.main",
        "bench",
        "suite",
        "--scenario",
        str(scenario),
        "--out-dir",
        str(out_dir),
        "--time-limit",
        "60",
        "--sa-iters",
        "2000",
        "--no-include-mip",
        "--no-include-ils",
        "--no-include-tabu",
    ]
    run_cmd(cmd, repo_root)
    summary = out_dir / "summary.csv"
    if not summary.exists():
        raise FileNotFoundError(summary)
    return summary


def collect_metrics(scenario_dir: Path) -> dict[str, Any]:
    blocks_csv = scenario_dir / "data" / "blocks.csv"
    machines_csv = scenario_dir / "data" / "machines.csv"
    blocks_df = pd.read_csv(blocks_csv)
    machines_df = pd.read_csv(machines_csv)
    scenario_yaml = scenario_dir / "scenario.yaml"
    num_days = None
    if scenario_yaml.exists():
        with scenario_yaml.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith("num_days"):
                    num_days = int(line.split(":", 1)[1].strip())
                    break
    return {
        "blocks": int(blocks_df.shape[0]),
        "machines": int(machines_df.shape[0]),
        "num_days": num_days,
    }


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = (
        args.out_dir
        if args.out_dir is not None
        else repo_root / "docs" / "softwarex" / "assets" / "data" / "scaling"
    ).resolve()
    datasets_dir = out_dir / "datasets"
    bench_dir = out_dir / "benchmarks"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    bench_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for tier in TIERS:
        print(f"[scaling] tier={tier.name}")
        dataset_path = datasets_dir / f"synthetic_{tier.name}"
        scenario_path = synth_bundle(repo_root, tier, dataset_path)
        summary_csv = bench_scenario(repo_root, scenario_path, bench_dir / tier.name)
        summary_df = pd.read_csv(summary_csv)
        sa_row = summary_df[summary_df["solver"] == "sa"].iloc[0]
        metrics = collect_metrics(dataset_path)
        rows.append(
            {
                "tier": tier.name,
                "blocks": int(metrics["blocks"]),
                "machines": int(metrics["machines"]),
                "num_days": int(metrics["num_days"]) if metrics["num_days"] is not None else None,
                "assignments": float(sa_row["assignments"]),
                "runtime_s": float(sa_row["runtime_s"]),
                "objective": float(sa_row["objective"]),
            }
        )

    summary_path = out_dir / "scaling_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path = out_dir / "scaling_summary.json"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    df = pd.DataFrame(rows)
    df.sort_values("blocks", inplace=True)
    plt.figure(figsize=(6, 4))
    plt.plot(df["blocks"], df["runtime_s"], marker="o")
    plt.xlabel("Blocks")
    plt.ylabel("SA runtime (s)")
    plt.title("Simulated annealing runtime vs. scenario size")
    for _, row in df.iterrows():
        plt.text(row["blocks"], row["runtime_s"], row["tier"], fontsize=8, ha="left", va="bottom")
    plt.grid(True, axis="both", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plot_path = out_dir / "runtime_vs_blocks.png"
    plt.savefig(plot_path, dpi=200)
    plt.close()
    print(f"[scaling] Wrote summary to {summary_path} and plot to {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
