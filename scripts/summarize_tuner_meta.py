#!/usr/bin/env python
"""Summarise tuner metadata stored in telemetry SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


def _normalise_budget(budget: dict[str, Any] | None) -> str:
    if not budget:
        return ""
    ordered = {key: budget[key] for key in sorted(budget)}
    return json.dumps(ordered, sort_keys=True)


def _normalise_config(config: dict[str, Any] | None) -> str:
    if not config:
        return ""
    limited = {key: config[key] for key in sorted(config) if key not in {"operators"}}
    return json.dumps(limited, sort_keys=True)


def summarise(sqlite_path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT run_id, scenario, tuner_meta_json
        FROM runs
        WHERE tuner_meta_json IS NOT NULL
        """
    ).fetchall()
    conn.close()

    records: list[dict[str, Any]] = []
    for row in rows:
        meta = json.loads(row["tuner_meta_json"] or "{}")
        algorithm = meta.get("algorithm") or "unknown"
        budget = _normalise_budget(meta.get("budget"))
        config = _normalise_config(meta.get("config"))
        progress = meta.get("progress") or {}
        records.append(
            {
                "run_id": row["run_id"],
                "scenario": row["scenario"],
                "algorithm": algorithm,
                "budget": budget,
                "config_snippet": config,
                "progress": json.dumps(progress, sort_keys=True) if progress else "",
            }
        )

    if not records:
        return pd.DataFrame(columns=["algorithm", "runs", "scenarios", "sample_budget", "sample_config"])

    df = pd.DataFrame(records)
    grouped = (
        df.groupby("algorithm")
        .agg(
            runs=("run_id", "count"),
            scenarios=("scenario", lambda values: len(set(values))),
            sample_budget=("budget", "first"),
            sample_config=("config_snippet", "first"),
        )
        .reset_index()
        .sort_values("algorithm")
    )
    return grouped


def render_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "*(no tuner_meta records found)*"
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        cells = []
        for header in headers:
            value = row[header]
            if value is None or (isinstance(value, float) and pd.isna(value)):
                cells.append("")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_path", type=Path, help="Path to telemetry runs SQLite database.")
    parser.add_argument("--out-csv", type=Path, help="Optional CSV output path.")
    parser.add_argument("--out-markdown", type=Path, help="Optional Markdown output path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    df = summarise(args.sqlite_path)

    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out_csv, index=False)

    if args.out_markdown:
        args.out_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.out_markdown.write_text(render_markdown(df) + "\n", encoding="utf-8")

    if not args.out_csv and not args.out_markdown:
        print(render_markdown(df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
