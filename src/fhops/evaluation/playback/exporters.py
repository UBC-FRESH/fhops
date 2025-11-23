"""Shared export utilities for playback summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from fhops.evaluation.playback.aggregates import machine_utilisation_summary

__all__ = [
    "export_playback",
    "render_markdown_summary",
    "playback_summary_metrics",
]


def export_playback(
    shift_df: pd.DataFrame,
    day_df: pd.DataFrame,
    *,
    shift_csv: Path | None = None,
    day_csv: Path | None = None,
    shift_parquet: Path | None = None,
    day_parquet: Path | None = None,
    summary_md: Path | None = None,
) -> dict[str, Any]:
    """Write playback summaries to the requested outputs.

    Parameters
    ----------
    shift_df, day_df:
        DataFrames produced by :func:`fhops.evaluation.playback.aggregates.shift_dataframe` and
        :func:`day_dataframe`.
    shift_csv, day_csv:
        Optional paths for CSV exports.
    shift_parquet, day_parquet:
        Optional paths for Parquet exports (requires ``pyarrow`` or ``fastparquet``).
    summary_md:
        Optional Markdown summary export (produced via :func:`render_markdown_summary`).

    Returns
    -------
    dict
        Scalar metrics from :func:`playback_summary_metrics` (samples, total production, etc.).
    """

    metrics = playback_summary_metrics(shift_df, day_df)

    if shift_csv:
        shift_csv.parent.mkdir(parents=True, exist_ok=True)
        shift_df.to_csv(shift_csv, index=False)
    if day_csv:
        day_csv.parent.mkdir(parents=True, exist_ok=True)
        day_df.to_csv(day_csv, index=False)

    if shift_parquet:
        _write_parquet(shift_df, shift_parquet)
    if day_parquet:
        _write_parquet(day_df, day_parquet)

    if summary_md:
        summary_md.parent.mkdir(parents=True, exist_ok=True)
        summary_md.write_text(render_markdown_summary(shift_df, day_df, metrics), encoding="utf-8")

    return metrics


def render_markdown_summary(
    shift_df: pd.DataFrame,
    day_df: pd.DataFrame,
    metrics: dict[str, Any] | None = None,
) -> str:
    """Return a Markdown-formatted playback summary."""

    metrics = metrics or playback_summary_metrics(shift_df, day_df)
    lines = [
        "# Playback Summary",
        "",
        f"- Samples: {metrics['samples']}",
        f"- Total production units: {metrics['total_production']:.2f}",
        f"- Total hours worked: {metrics['total_hours']:.2f}",
        f"- Average utilisation (day-level): {metrics['average_utilisation']:.2f}",
        f"- Total mobilisation cost: {metrics['mobilisation_cost']:.2f}",
        "",
        "## Top Machines by Utilisation",
        "",
    ]

    utilisation = machine_utilisation_summary(shift_df)
    utilisation_preview = utilisation.sort_values(by=["utilisation_ratio"], ascending=False).head(
        10
    )

    if not utilisation_preview.empty:
        try:
            lines.append(utilisation_preview.to_markdown(index=False))
        except ImportError:
            lines.append("``````\n" + utilisation_preview.to_csv(index=False) + "``````")
    else:
        lines.append("(no utilisation data)")

    lines.extend(["", "## Day Snapshot (first 10 rows)", ""])
    day_preview = day_df.head(10).copy()
    if not day_preview.empty:
        day_preview["utilisation_ratio"] = day_preview["utilisation_ratio"].map(
            lambda x: f"{x:.2f}" if pd.notna(x) else ""
        )
        try:
            lines.append(day_preview.to_markdown(index=False))
        except ImportError:
            lines.append("``````\n" + day_preview.to_csv(index=False) + "``````")
    else:
        lines.append("(no day-level data)")

    return "\n".join(lines)


def playback_summary_metrics(shift_df: pd.DataFrame, day_df: pd.DataFrame) -> dict[str, Any]:
    """Compute scalar summary metrics (production, hours, mobilisation, utilisation)."""

    samples = int(day_df["sample_id"].nunique()) if "sample_id" in day_df.columns else 1
    total_production = float(day_df.get("production_units", pd.Series(dtype=float)).sum())
    total_hours = float(day_df.get("total_hours", pd.Series(dtype=float)).sum())
    mobilisation_cost = float(day_df.get("mobilisation_cost", pd.Series(dtype=float)).sum())
    utilisation_series = day_df.get("utilisation_ratio")
    average_utilisation = (
        float(utilisation_series.dropna().mean()) if utilisation_series is not None else 0.0
    )

    return {
        "samples": samples or 1,
        "total_production": total_production,
        "total_hours": total_hours,
        "mobilisation_cost": mobilisation_cost,
        "average_utilisation": average_utilisation,
    }


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to Parquet, ensuring either pyarrow or fastparquet is installed."""
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        try:
            import fastparquet  # noqa: F401
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError("Parquet export requires pyarrow or fastparquet") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
