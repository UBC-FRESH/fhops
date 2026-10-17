#!/usr/bin/env python
"""Materialize manuscript-ready tables (solver performance + tuning leaderboard)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Literal

import pandas as pd

SCENARIOS = [
    {
        "slug": "tiny7",
        "label": "Tiny7 (ground-based)",
        "sense": "maximize",
        "comparison_key": "baseline:tiny7",
        "report_key": "FHOPS Tiny7",
    },
    {
        "slug": "small21",
        "label": "Small21 (ground-based)",
        "sense": "maximize",
        "comparison_key": "baseline:small21",
        "report_key": "FHOPS Small21",
    },
    {
        "slug": "med42",
        "label": "Med42 (ground-based)",
        # FHOPS heuristics maximise the objective on every scenario; med42 scores are negative
        # (penalty/mobilisation dominated), not minimised.
        "sense": "maximize",
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


TUNER_SOURCES = {
    "cli.tune-random": "random",
    "cli.tune-grid": "grid",
    "cli.tune-bayes": "bayes",
    "benchmark.ils": "ils",
    "benchmark.tabu": "tabu",
}
TUNER_LABELS = {"bayes": "Bayes", "grid": "Grid", "random": "Random", "ils": "ILS", "tabu": "Tabu"}
# (count key, unit, iterations key) per tuner budget record in runs.jsonl ``tuner_meta.budget``.
BUDGET_KEYS = (
    ("trials_total", "trial", "iters_per_trial"),
    ("total_configs", "config", "iters_per_config"),
    ("runs_total", "run", "iters_per_run"),
)
DELTA_COL = r"$\Delta$ vs SA default"


def _stack(*lines: str, align: str = "r") -> str:
    return r"\begin{tabular}[b]{@{}" + align + "@{}}" + r"\\".join(lines) + r"\end{tabular}"


# Ragged-right paragraph columns (``array`` package) keep the table about one text width wide.
_RAGGED = r">{\raggedright\arraybackslash}"
_RAGGED_SMALL = r">{\raggedright\arraybackslash\footnotesize}"
TEX_LEADERBOARD_COLUMNS = (
    _RAGGED
    + r"p{0.13\linewidth}lrrr"
    + _RAGGED_SMALL
    + r"p{0.08\linewidth}"
    + _RAGGED_SMALL
    + r"p{0.22\linewidth}"
)
TEX_LEADERBOARD_HEADER = (
    " & ".join(
        [
            "Scenario",
            "Tuner",
            _stack("Best", "objective"),
            _stack(r"$\Delta$ vs", "SA default"),
            _stack("Mean", "runtime (s)"),
            "Budget",
            "Key settings",
        ]
    )
    + r" \\"
)


def _scenario_meta(slug: str) -> dict:
    for meta in SCENARIOS:
        if meta["slug"] == slug:
            return meta
    raise KeyError(slug)


def _format_float(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _escape_latex(text: str) -> str:
    """Return a LaTeX-safe representation of ``text``."""

    if not text:
        return text

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }

    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


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


def default_sa_iterations(bench_dir: Path) -> dict[str, int]:
    """Return the SA default benchmark budget (``iters``) per scenario slug."""
    budgets: dict[str, int] = {}
    for meta in SCENARIOS:
        df = pd.read_csv(bench_dir / meta["slug"] / "summary.csv")
        row = _select_solver_row(df, "sa", meta["sense"])
        budgets[meta["slug"]] = int(row["iters"])
    return budgets


def load_tuning_runs(runs_path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group the tuning ``run`` records of ``runs.jsonl`` by (scenario, tuner)."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("record_type") != "run":
            continue
        algorithm = TUNER_SOURCES.get((record.get("context") or {}).get("source", ""))
        if algorithm is None:
            continue
        grouped.setdefault((record["scenario"], algorithm), []).append(record)
    return grouped


def format_budget(budget: dict[str, Any]) -> str:
    """Render a ``tuner_meta.budget`` record as ``<n> <unit>s $\\times$ <iters> iters``."""
    for count_key, unit, iters_key in BUDGET_KEYS:
        if count_key in budget and iters_key in budget:
            count = int(budget[count_key])
            plural = "" if count == 1 else "s"
            return f"{count} {unit}{plural} $\\times$ {int(budget[iters_key])} iters"
    raise ValueError(f"Unrecognised tuner budget record: {budget}")


def _tuner_budget(runs: list[dict[str, Any]]) -> str:
    budgets = {json.dumps((r.get("tuner_meta") or {}).get("budget"), sort_keys=True) for r in runs}
    if len(budgets) != 1:
        raise ValueError(f"Tuning runs disagree on their budget: {sorted(budgets)}")
    return format_budget(json.loads(budgets.pop()))


def compact_settings(config: str) -> str:
    """Shorten a tuner config for the table.

    ``iters=`` is dropped (the budget column shows it), ``operators=(a:w, ...)`` becomes
    ``operator weights a=w, ...`` and long decimals are rounded to two places.
    """
    parts: list[str] = []
    for part in config.split("; "):
        if not part or part.startswith("iters="):
            continue
        match = re.fullmatch(r"operators=\((.*)\)", part)
        if match:
            weights = [item.strip().replace(":", "=", 1) for item in match.group(1).split(",")]
            part = "operator weights " + ", ".join(weights)
        parts.append(part)
    text = "; ".join(parts)
    return re.sub(r"\d+\.\d{3,}", lambda m: f"{float(m.group(0)):.2f}", text)


def _run_settings(run: dict[str, Any]) -> str:
    config = (run.get("tuner_meta") or {}).get("config") or {}
    return "; ".join(f"{key}={config[key]}" for key in sorted(config))


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
    *,
    runs_path: Path | None = None,
    sa_default_iters: dict[str, int] | None = None,
) -> None:
    """Write ``tuning_leaderboard.{csv,tex}``: best tuner per scenario with its budget.

    ``runs_path`` defaults to ``telemetry/runs.jsonl`` next to ``comparison_path``. When
    ``sa_default_iters`` is given, the LaTeX table ends with a note row stating the SA default
    benchmark budgets that Delta is measured against.
    """
    comparison_df = pd.read_csv(comparison_path)
    report_df = pd.read_csv(report_path)
    runs = load_tuning_runs(runs_path or comparison_path.parent / "telemetry" / "runs.jsonl")

    records: list[dict[str, object]] = []
    ties: list[str] = []

    for meta in SCENARIOS:
        comp_subset = comparison_df[comparison_df["scenario"] == meta["comparison_key"]]
        if comp_subset.empty:
            continue
        ascending = meta["sense"] == "minimize"
        best_idx = (
            comp_subset["best_objective"].idxmin()
            if ascending
            else comp_subset["best_objective"].idxmax()
        )
        best_row = comp_subset.loc[best_idx]
        algorithm = str(best_row["algorithm"])
        tied = int(
            (comp_subset["best_objective"] - best_row["best_objective"]).abs().le(1e-6).sum()
        )
        if tied > 1:
            ties.append(f"{meta['label'].split(' ')[0]} ({tied} tuners)")

        delta = (
            default_sa_objectives[meta["slug"]] - best_row["best_objective"]
            if ascending
            else best_row["best_objective"] - default_sa_objectives[meta["slug"]]
        )

        tuner_runs = runs.get((meta["report_key"], algorithm), [])
        if not tuner_runs:
            raise ValueError(f"No tuning runs for {meta['report_key']} / {algorithm}")

        report_subset = report_df[
            (report_df["scenario"] == meta["report_key"]) & (report_df["algorithm"] == algorithm)
        ]
        best_config = ""
        if not report_subset.empty and not pd.isna(report_subset["best_config"].iloc[0]):
            best_config = str(report_subset["best_config"].iloc[0])
        if not best_config:
            # ILS/Tabu runs are not in tuner_report.csv; use the best run's tuner settings.
            pick = min if ascending else max
            best_run = pick(tuner_runs, key=lambda r: float(r["metrics"]["objective"]))
            best_config = _run_settings(best_run)

        records.append(
            {
                "Scenario": meta["label"],
                "Tuner": TUNER_LABELS.get(algorithm, algorithm.capitalize()),
                "Best Objective": best_row["best_objective"],
                DELTA_COL: delta,
                "Mean Runtime (s)": best_row["mean_runtime"],
                "Budget": _tuner_budget(tuner_runs),
                "Key Settings": compact_settings(best_config),
            }
        )

    if not records:
        raise RuntimeError("No tuning records were produced.")

    df = pd.DataFrame.from_records(records)
    formatted = df.copy()
    for col in ["Best Objective", DELTA_COL, "Mean Runtime (s)"]:
        formatted[col] = formatted[col].apply(_format_float)
    formatted["Key Settings"] = formatted["Key Settings"].apply(_escape_latex)

    _ensure_dir(out_dir)
    formatted.to_csv(out_dir / "tuning_leaderboard.csv", index=False)
    latex = formatted.to_latex(
        index=False,
        escape=False,
        column_format=TEX_LEADERBOARD_COLUMNS,
    )
    # Two-line headers keep the numeric columns narrow (the CSV keeps one-line names).
    header = " & ".join(formatted.columns) + r" \\"
    latex = latex.replace(header, TEX_LEADERBOARD_HEADER, 1)
    if sa_default_iters:
        budgets = ", ".join(
            f"{sa_default_iters[meta['slug']]} ({meta['label'].split(' ')[0]})"
            for meta in SCENARIOS
            if meta["slug"] in sa_default_iters
        )
        note = (
            r"\multicolumn{7}{p{0.95\linewidth}}{\footnotesize Budget: tuning runs of the best "
            r"tuner (SA iterations per Bayesian trial, grid configuration or random run; ILS/Tabu "
            r"iterations). $\Delta$ = best tuned objective minus the SA default benchmark "
            r"objective, whose budget is far larger (SA iterations: "
            + budgets
            + r"); objectives are maximised."
            + (
                " Ties (same best objective): "
                + ", ".join(ties)
                + "; the first tuner in alphabetical order is listed."
                if ties
                else ""
            )
            + r"} \\"
        )
        latex = latex.replace("\\bottomrule\n", "\\bottomrule\n" + note + "\n", 1)
    (out_dir / "tuning_leaderboard.tex").write_text(latex, encoding="utf-8")


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
    build_tuning_leaderboard_table(
        comp_path,
        report_path,
        default_sa,
        tables_dir,
        sa_default_iters=default_sa_iterations(bench_dir),
    )
    print(f"[tables] Wrote solver + tuning tables to {tables_dir}")


if __name__ == "__main__":
    main()
