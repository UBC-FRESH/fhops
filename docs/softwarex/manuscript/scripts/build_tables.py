#!/usr/bin/env python
"""Materialize manuscript-ready tables (solver performance + tuning leaderboard)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

SCENARIOS = [
    {
        "slug": "minitoy",
        "label": "MiniToy (ground-based)",
        "sense": "maximize",
        "comparison_key": "baseline:minitoy",
        "report_key": "FHOPS MiniToy",
    },
    {
        "slug": "med42",
        "label": "Med42 (mixed skyline/tethered)",
        "sense": "minimize",
        "comparison_key": "baseline:med42",
        "report_key": "FHOPS Medium42",
    },
    {
        "slug": "synthetic_small",
        "label": "Synthetic-small",
        "sense": "maximize",
        "comparison_key": "synthetic-small",
        "report_key": "synthetic-small",
    },
]


def _scenario_meta(slug: str) -> dict:
    for meta in SCENARIOS:
        if meta["slug"] == slug:
            return meta
    raise KeyError(slug)


def _format_float(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _select_solver_row(
    df: pd.DataFrame,
    solver: str,
    sense: Literal["maximize", "minimize"],
) -> pd.Series:
    subset = df[df["solver"] == solver].copy()
    if subset.empty:
        raise ValueError(f"No rows found for solver={solver}")

    if solver == "sa":
        preset_col = subset["preset_label"].fillna("").str.lower()
        target = subset[preset_col.isin({"default", ""})]
        if target.empty:
            target = subset
        subset = target

    ascending = sense == "minimize"
    subset = subset.sort_values("objective", ascending=ascending)
    return subset.iloc[0]


def build_solver_performance_table(bench_dir: Path, out_dir: Path) -> dict[str, float]:
    records: list[dict[str, object]] = []
    default_sa_objectives: dict[str, float] = {}

    for meta in SCENARIOS:
        summary_path = bench_dir / meta["slug"] / "summary.csv"
        if not summary_path.exists():
            raise FileNotFoundError(summary_path)
        df = pd.read_csv(summary_path)

        for solver in ("sa", "ils", "tabu"):
            row = _select_solver_row(df, solver, meta["sense"])
            if solver == "sa":
                default_sa_objectives[meta["slug"]] = float(row["objective"])

            mob_cost = row.get("kpi_mobilisation_cost", float("nan"))
            records.append(
                {
                    "Scenario": meta["label"],
                    "Solver": solver.upper(),
                    "Objective": row["objective"],
                    "Runtime (s)": row["runtime_s"],
                    "Assignments": row["assignments"],
                    "Production (m³)": row.get("kpi_total_production", float("nan")),
                    "Mobilisation Cost (CAD)": mob_cost,
                }
            )

    table_df = pd.DataFrame.from_records(records)

    table_df["Mobilisation Cost (CAD)"] = table_df["Mobilisation Cost (CAD)"].fillna(0.0)

    formatted_df = table_df.copy()
    for col in [
        "Objective",
        "Runtime (s)",
        "Production (m³)",
        "Mobilisation Cost (CAD)",
    ]:
        formatted_df[col] = formatted_df[col].apply(_format_float)
    formatted_df["Assignments"] = formatted_df["Assignments"].astype(int)

    _ensure_dir(out_dir)
    formatted_df.to_csv(out_dir / "solver_performance.csv", index=False)
    formatted_df.to_latex(
        out_dir / "solver_performance.tex",
        index=False,
        escape=False,
        column_format="llrrrrr",
    )
    return default_sa_objectives


def build_tuning_leaderboard_table(
    comparison_path: Path,
    report_path: Path,
    default_sa_objectives: dict[str, float],
    out_dir: Path,
) -> None:
    comparison_df = pd.read_csv(comparison_path)
    report_df = pd.read_csv(report_path)

    records: list[dict[str, object]] = []

    for meta in SCENARIOS:
        comp_subset = comparison_df[comparison_df["scenario"] == meta["comparison_key"]]
        if comp_subset.empty:
            continue
        ascending = meta["sense"] == "minimize"
        best_idx = comp_subset["best_objective"].idxmin() if ascending else comp_subset["best_objective"].idxmax()
        best_row = comp_subset.loc[best_idx]

        delta = (
            default_sa_objectives[meta["slug"]] - best_row["best_objective"]
            if ascending
            else best_row["best_objective"] - default_sa_objectives[meta["slug"]]
        )

        report_subset = report_df[
            (report_df["scenario"] == meta["report_key"])
            & (report_df["algorithm"] == best_row["algorithm"])
        ]
        best_config = report_subset["best_config"].iloc[0] if not report_subset.empty else ""

        records.append(
            {
                "Scenario": meta["label"],
                "Tuner": best_row["algorithm"].capitalize(),
                "Best Objective": best_row["best_objective"],
                "Δ vs SA default": delta,
                "Mean Runtime (s)": best_row["mean_runtime"],
                "Key Settings": best_config,
            }
        )

    if not records:
        raise RuntimeError("No tuning records were produced.")

    df = pd.DataFrame.from_records(records)
    formatted = df.copy()
    for col in ["Best Objective", "Δ vs SA default", "Mean Runtime (s)"]:
        formatted[col] = formatted[col].apply(_format_float)

    _ensure_dir(out_dir)
    formatted.to_csv(out_dir / "tuning_leaderboard.csv", index=False)
    formatted.to_latex(
        out_dir / "tuning_leaderboard.tex",
        index=False,
        escape=False,
        column_format="llllll",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
    )
    parser.add_argument(
        "--tables-dir",
        type=Path,
        default=None,
        help="Optional override for tables directory (default: docs/softwarex/assets/data/tables)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root: Path = args.repo_root
    tables_dir = args.tables_dir or repo_root / "docs/softwarex/assets/data/tables"
    bench_dir = repo_root / "docs/softwarex/assets/data/benchmarks"
    comp_path = repo_root / "docs/softwarex/assets/data/tuning/tuner_comparison.csv"
    report_path = repo_root / "docs/softwarex/assets/data/tuning/tuner_report.csv"

    default_sa = build_solver_performance_table(bench_dir, tables_dir)
    build_tuning_leaderboard_table(comp_path, report_path, default_sa, tables_dir)
    print(f"[tables] Wrote solver + tuning tables to {tables_dir}")


if __name__ == "__main__":
    main()
