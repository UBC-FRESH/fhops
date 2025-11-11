#!/usr/bin/env python
"""Aggregate multiple tuner_report.csv files and compare objectives across runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


def _parse_report_arg(entry: str) -> tuple[str, Path]:
    if "=" in entry:
        label, path_str = entry.split("=", 1)
        label = label.strip()
        path = Path(path_str.strip())
    else:
        path = Path(entry.strip())
        label = path.stem
    if path.is_dir():
        path = path / "tuner_report.csv"
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    return label, path


def _load_report(label: str, path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"algorithm", "scenario", "best_objective", "mean_objective", "runs"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Report {path} missing columns: {sorted(missing)}")
    df = df.copy()
    df["algorithm"] = df["algorithm"].str.lower().str.strip()
    df["scenario"] = df["scenario"].str.strip()
    df.rename(
        columns={
            "best_objective": f"best_{label}",
            "mean_objective": f"mean_{label}",
            "runs": f"runs_{label}",
        },
        inplace=True,
    )
    subset = ["algorithm", "scenario", f"best_{label}", f"mean_{label}", f"runs_{label}"]
    return df[subset]


def _merge_reports(reports: Iterable[pd.DataFrame]) -> pd.DataFrame:
    iterator = iter(reports)
    try:
        combined = next(iterator)
    except StopIteration:
        raise ValueError("At least one report is required.")
    for df in iterator:
        combined = combined.merge(df, on=["algorithm", "scenario"], how="outer")
    combined.sort_values(["scenario", "algorithm"], inplace=True)
    return combined.reset_index(drop=True)


def _format_markdown(df: pd.DataFrame, labels: list[str]) -> str:
    headers = ["Algorithm", "Scenario"]
    for label in labels:
        headers.extend(
            [
                f"Best ({label})",
                f"Δ Best ({label})" if label != labels[0] else "",
                f"Mean ({label})",
                f"Runs ({label})",
            ]
        )
    headers = [h for h in headers if h]

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    baseline = labels[0]
    for _, row in df.iterrows():
        cells = [row["algorithm"], row["scenario"]]
        base_best = row.get(f"best_{baseline}")
        for label in labels:
            best_val = row.get(f"best_{label}")
            mean_val = row.get(f"mean_{label}")
            runs_val = row.get(f"runs_{label}")
            cells.append(_format_number(best_val))
            if label != baseline:
                diff = None
                if pd.notna(best_val) and pd.notna(base_best):
                    diff = best_val - base_best
                cells.append(_format_number(diff, prefix="+"))
            cells.append(_format_number(mean_val))
            cells.append(str(int(runs_val)) if pd.notna(runs_val) else "")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _format_number(value, prefix: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        return f"{prefix}{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help="Report path (or label=path). Directories default to tuner_report.csv.",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        help="Optional CSV output path for the combined report.",
    )
    parser.add_argument(
        "--out-markdown",
        type=Path,
        help="Optional Markdown output path for the combined report.",
    )
    parser.add_argument(
        "--out-chart",
        type=Path,
        help="Optional HTML path for an Altair chart comparing best objectives.",
    )
    args = parser.parse_args(argv)

    labels: list[str] = []
    frames: list[pd.DataFrame] = []
    for entry in args.report:
        label, path = _parse_report_arg(entry)
        labels.append(label)
        frames.append(_load_report(label, path))

    combined = _merge_reports(frames)
    baseline = labels[0]
    for label in labels[1:]:
        combined[f"best_delta_{label}"] = (
            combined[f"best_{label}"] - combined[f"best_{baseline}"]
        )

    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(args.out_csv, index=False)

    markdown = _format_markdown(combined, labels)
    if args.out_markdown:
        args.out_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.out_markdown.write_text(markdown + "\n", encoding="utf-8")

    if args.out_chart:
        try:
            import altair as alt
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SystemExit("Altair is required for --out-chart support.") from exc

        chart_records: list[dict[str, object]] = []
        for _, row in combined.iterrows():
            for label in labels:
                best_val = row.get(f"best_{label}")
                if pd.notna(best_val):
                    chart_records.append(
                        {
                            "algorithm": row["algorithm"],
                            "scenario": row["scenario"],
                            "label": label,
                            "best_objective": best_val,
                        }
                    )
        chart_df = pd.DataFrame(chart_records)
        if not chart_df.empty:
            chart = (
                alt.Chart(chart_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("label:N", title="Report"),
                    y=alt.Y("best_objective:Q", title="Best Objective"),
                    color=alt.Color("algorithm:N", title="Algorithm"),
                    row=alt.Row("scenario:N", title="Scenario"),
                )
                .properties(width=250, height=180)
            )
            args.out_chart.parent.mkdir(parents=True, exist_ok=True)
            chart.save(args.out_chart, embed_options={"actions": False})

    if not args.out_csv and not args.out_markdown:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
