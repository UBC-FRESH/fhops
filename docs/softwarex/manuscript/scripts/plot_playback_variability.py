#!/usr/bin/env python3
"""Generate playback robustness figure comparing deterministic vs stochastic utilisation."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

SCENARIOS = [
    ("tiny7", "Tiny7"),
    ("med42", "Med42"),
    ("synthetic_small", "Synthetic-small"),
]
SOLVERS = ("sa", "ils")
MODES = ("deterministic", "stochastic")
COLORS = {"deterministic": "#4c72b0", "stochastic": "#dd8452"}
# The manuscript (elsarticle preprint, 12pt) includes the figure at \linewidth = 390 pt (5.4 in).
# Drawing at that width (minus the saved padding) keeps the scale factor >= 1, so FONT_SIZE is the
# minimum printed text size; wider journal layouts only enlarge it.
FIGSIZE_IN = (5.35, 2.4)
FONT_SIZE = 9
SAVE_PAD_IN = 0.02


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


def load_utilisation(day_csv: Path, mode: str) -> tuple[float, float, int]:
    """Return mean/std day-level utilisation and the number of samples in ``day_csv``.

    Deterministic runs report the mean of ``utilisation_ratio`` over all days (std 0). Stochastic
    runs average each sample's days first, then report the mean and population std across samples.
    """
    df = pd.read_csv(day_csv)
    if mode == "deterministic":
        mean = df["utilisation_ratio"].mean()
        return mean, 0.0, 1
    grouped = df.groupby("sample_id")["utilisation_ratio"].mean()
    mean = grouped.mean()
    std = grouped.std(ddof=0)
    return mean, std, int(grouped.size)


def collect_metrics(playback_dir: Path) -> pd.DataFrame:
    records: list[dict] = []
    for slug, label in SCENARIOS:
        for solver in SOLVERS:
            for mode in MODES:
                day_csv = playback_dir / slug / solver / mode / "day.csv"
                if not day_csv.exists():
                    continue
                mean, std, samples = load_utilisation(day_csv, mode)
                records.append(
                    {
                        "Scenario": label,
                        "solver": solver.upper(),
                        "mode": mode,
                        "mean_util": mean,
                        "std_util": std,
                        "samples": samples,
                    }
                )
    if not records:
        raise RuntimeError(f"No playback day.csv files found under {playback_dir}")
    return pd.DataFrame.from_records(records)


def plot(df: pd.DataFrame, out_path: Path) -> None:
    """Draw one panel per scenario sized for the manuscript text width (``FIGSIZE_IN``).

    All text is set at ``FONT_SIZE`` points at print size, the legend sits in one row above the
    panels (inside the saved canvas), and no suptitle is drawn because the manuscript caption
    describes the figure.
    """
    scenarios = list(df["Scenario"].unique())
    solvers = [solver.upper() for solver in SOLVERS]
    stochastic_samples = df.loc[df["mode"] == "stochastic", "samples"]
    stochastic_label = "Stochastic (mean ± SD"
    if not stochastic_samples.empty and stochastic_samples.nunique() == 1:
        stochastic_label += f", n = {int(stochastic_samples.iloc[0])}"
    stochastic_label += ")"
    labels = {"deterministic": "Deterministic", "stochastic": stochastic_label}

    with plt.rc_context(
        {
            "font.size": FONT_SIZE,
            "axes.titlesize": FONT_SIZE,
            "axes.labelsize": FONT_SIZE,
            "xtick.labelsize": FONT_SIZE,
            "ytick.labelsize": FONT_SIZE,
            "legend.fontsize": FONT_SIZE,
        }
    ):
        fig, axes = plt.subplots(
            1, len(scenarios), figsize=FIGSIZE_IN, sharey=True, layout="constrained"
        )
        if len(scenarios) == 1:
            axes = [axes]

        width = 0.38
        x_positions = list(range(len(solvers)))
        for ax, scenario in zip(axes, scenarios):
            sub = df[df["Scenario"] == scenario]
            for idx, mode in enumerate(MODES):
                offset = (idx - 0.5) * width
                mode_data = sub[sub["mode"] == mode].set_index("solver").reindex(solvers)
                ax.bar(
                    [x + offset for x in x_positions],
                    mode_data["mean_util"],
                    width=width,
                    color=COLORS[mode],
                    label=labels[mode],
                    yerr=mode_data["std_util"] if mode == "stochastic" else None,
                    capsize=3 if mode == "stochastic" else 0,
                    error_kw={"elinewidth": 1.0, "capthick": 1.0},
                    zorder=2,
                )
            ax.set_xticks(x_positions)
            ax.set_xticklabels(solvers)
            ax.set_xlim(-0.6, len(solvers) - 0.4)
            ax.set_ylim(0, 1.0)
            ax.set_title(scenario)
            ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)
            ax.set_axisbelow(True)

        axes[0].set_ylabel("Mean day-level utilisation")
        handles, legend_labels = axes[0].get_legend_handles_labels()
        legend = fig.legend(
            handles,
            legend_labels,
            loc="outside upper center",
            ncol=len(MODES),
            frameon=False,
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs = {
            "bbox_inches": "tight",
            "bbox_extra_artists": [legend],
            "pad_inches": SAVE_PAD_IN,
        }
        fig.savefig(out_path, dpi=300, **save_kwargs)
        # Drop the PDF creation timestamp so reruns on unchanged data are byte-identical.
        fig.savefig(out_path.with_suffix(".pdf"), metadata={"CreationDate": None}, **save_kwargs)
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
