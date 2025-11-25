#!/usr/bin/env python3
"""Generate playback robustness figure comparing deterministic vs stochastic utilisation."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

SCENARIOS = [
    ("minitoy", "MiniToy"),
    ("med42", "Med42"),
    ("synthetic_small", "Synthetic-small"),
]
SOLVERS = ("sa", "ils")
MODES = ("deterministic", "stochastic")
COLORS = {"deterministic": "#4c72b0", "stochastic": "#dd8452"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="FHOPS repository root.",
    )
    parser.add_argument(
        "--playback-dir",
        type=Path,
        default=None,
        help="Playback asset directory (default: docs/softwarex/assets/data/playback).",
    )
    parser.add_argument(
        "--out-path",
        type=Path,
        default=None,
        help="Figure output path (default: docs/softwarex/assets/data/playback/utilisation_robustness.png).",
    )
    return parser.parse_args()


def load_utilisation(day_csv: Path, mode: str) -> tuple[float, float]:
    df = pd.read_csv(day_csv)
    if mode == "deterministic":
        mean = df["utilisation_ratio"].mean()
        return mean, 0.0
    grouped = df.groupby("sample_id")["utilisation_ratio"].mean()
    mean = grouped.mean()
    std = grouped.std(ddof=0)
    return mean, std


def collect_metrics(playback_dir: Path) -> pd.DataFrame:
    records: list[dict] = []
    for slug, label in SCENARIOS:
        for solver in SOLVERS:
            for mode in MODES:
                day_csv = playback_dir / slug / solver / mode / "day.csv"
                if not day_csv.exists():
                    continue
                mean, std = load_utilisation(day_csv, mode)
                records.append(
                    {
                        "Scenario": label,
                        "solver": solver.upper(),
                        "mode": mode,
                        "mean_util": mean,
                        "std_util": std,
                    }
                )
    if not records:
        raise RuntimeError(f"No playback day.csv files found under {playback_dir}")
    return pd.DataFrame.from_records(records)


def plot(df: pd.DataFrame, out_path: Path) -> None:
    scenarios = df["Scenario"].unique()
    fig, axes = plt.subplots(1, len(scenarios), figsize=(12, 4), sharey=True)
    if len(scenarios) == 1:
        axes = [axes]

    for ax, scenario in zip(axes, scenarios):
        sub = df[df["Scenario"] == scenario]
        x_positions = range(len(SOLVERS))
        width = 0.35
        for idx, mode in enumerate(MODES):
            offset = (idx - 0.5) * width
            mode_data = sub[sub["mode"] == mode]
            ax.bar(
                [x + offset for x in x_positions],
                mode_data["mean_util"],
                width=width,
                color=COLORS[mode],
                label=mode.capitalize() if scenario == scenarios[0] else "",
                yerr=mode_data["std_util"],
                capsize=3 if mode == "stochastic" else 0,
            )
        ax.set_xticks(list(x_positions))
        ax.set_xticklabels(SOLVERS)
        ax.set_ylim(0, 1.05)
        ax.set_title(scenario)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    axes[0].set_ylabel("Mean utilisation")
    fig.suptitle("Playback robustness: deterministic vs stochastic utilisation")
    fig.legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.05))
    fig.tight_layout(rect=(0, 0, 1, 0.95))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    playback_dir = (
        args.playback_dir
        if args.playback_dir is not None
        else repo_root / "docs" / "softwarex" / "assets" / "data" / "playback"
    ).resolve()
    out_path = (
        args.out_path if args.out_path is not None else playback_dir / "utilisation_robustness.png"
    ).resolve()
    df = collect_metrics(playback_dir)
    plot(df, out_path)
    print(f"[playback-figure] Wrote playback robustness figure to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
