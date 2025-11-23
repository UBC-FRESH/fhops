"""Aggregation helpers for playback summaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict

import pandas as pd

from fhops.evaluation.playback.core import DaySummary, PlaybackResult, ShiftSummary
from fhops.evaluation.playback.stochastic import EnsembleResult

__all__ = [
    "SHIFT_SUMMARY_COLUMNS",
    "DAY_SUMMARY_COLUMNS",
    "shift_dataframe",
    "day_dataframe",
    "shift_dataframe_from_ensemble",
    "day_dataframe_from_ensemble",
    "machine_utilisation_summary",
]

SHIFT_SUMMARY_COLUMNS = [
    "day",
    "shift_id",
    "machine_id",
    "machine_role",
    "sample_id",
    "production_units",
    "total_hours",
    "idle_hours",
    "mobilisation_cost",
    "sequencing_violations",
    "blackout_conflicts",
    "available_hours",
    "utilisation_ratio",
    "downtime_hours",
    "downtime_events",
    "weather_severity_total",
]

DAY_SUMMARY_COLUMNS = [
    "day",
    "sample_id",
    "production_units",
    "total_hours",
    "idle_hours",
    "mobilisation_cost",
    "completed_blocks",
    "blackout_conflicts",
    "sequencing_violations",
    "available_hours",
    "utilisation_ratio",
    "downtime_hours",
    "downtime_events",
    "weather_severity_total",
]


def _summary_dataframe(
    summaries: Sequence[ShiftSummary | DaySummary],
    *,
    columns: Sequence[str],
) -> pd.DataFrame:
    """Convert a collection of ``ShiftSummary``/``DaySummary`` into a DataFrame.

    Parameters
    ----------
    summaries:
        Iterable of dataclass instances produced by playback.
    columns:
        Column ordering expected by the consumer (``SHIFT_SUMMARY_COLUMNS`` or
        ``DAY_SUMMARY_COLUMNS``).
    """
    if not summaries:
        return pd.DataFrame(columns=list(columns))
    rows = [asdict(summary) for summary in summaries]
    df = pd.DataFrame(rows)
    return df.reindex(columns=list(columns))


def shift_dataframe(result: PlaybackResult) -> pd.DataFrame:
    """Return the shift-level playback summaries as a DataFrame.

    Parameters
    ----------
    result:
        :class:`PlaybackResult` returned by :func:`fhops.evaluation.playback.core.run_playback`.
    """
    return _summary_dataframe(result.shift_summaries, columns=SHIFT_SUMMARY_COLUMNS)


def day_dataframe(result: PlaybackResult) -> pd.DataFrame:
    """Return the day-level playback summaries as a DataFrame."""
    return _summary_dataframe(result.day_summaries, columns=DAY_SUMMARY_COLUMNS)


def shift_dataframe_from_ensemble(
    ensemble: EnsembleResult,
    *,
    include_base: bool = False,
) -> pd.DataFrame:
    """Concatenate shift summaries from a stochastic ensemble.

    Parameters
    ----------
    ensemble:
        Result of :func:`fhops.evaluation.playback.stochastic.run_stochastic_playback`.
    include_base:
        When ``True``, include the base deterministic result in addition to samples.
    """

    frames: list[pd.DataFrame] = []
    if include_base:
        frames.append(shift_dataframe(ensemble.base_result))
    for sample in ensemble.samples:
        frames.append(shift_dataframe(sample.result))
    if not frames:
        return pd.DataFrame(columns=SHIFT_SUMMARY_COLUMNS)
    combined = pd.concat(frames, ignore_index=True)
    return combined.reindex(columns=SHIFT_SUMMARY_COLUMNS)


def day_dataframe_from_ensemble(
    ensemble: EnsembleResult,
    *,
    include_base: bool = False,
) -> pd.DataFrame:
    """Concatenate day-level summaries from an ensemble."""

    frames: list[pd.DataFrame] = []
    if include_base:
        frames.append(day_dataframe(ensemble.base_result))
    for sample in ensemble.samples:
        frames.append(day_dataframe(sample.result))
    if not frames:
        return pd.DataFrame(columns=DAY_SUMMARY_COLUMNS)
    combined = pd.concat(frames, ignore_index=True)
    return combined.reindex(columns=DAY_SUMMARY_COLUMNS)


def machine_utilisation_summary(shift_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate shift summaries into per-machine utilisation metrics.

    Parameters
    ----------
    shift_df:
        DataFrame produced by :func:`shift_dataframe` or ``*_from_ensemble``; must include
        ``total_hours`` and ``available_hours`` columns.

    Returns
    -------
    pandas.DataFrame
        One row per ``(sample_id, machine_id)`` with total/available hours, utilisation ratio,
        production, mobilisation cost, and constraint violation counts.
    """

    if shift_df.empty:
        return pd.DataFrame(
            columns=[
                "sample_id",
                "machine_id",
                "total_hours",
                "available_hours",
                "utilisation_ratio",
                "production_units",
            ]
        )
    group_cols = [col for col in ["sample_id", "machine_id"] if col in shift_df.columns]
    aggregated = (
        shift_df.groupby(group_cols, dropna=False, as_index=False)
        .agg(
            total_hours=("total_hours", "sum"),
            available_hours=("available_hours", "sum"),
            production_units=("production_units", "sum"),
            mobilisation_cost=("mobilisation_cost", "sum"),
            blackout_conflicts=("blackout_conflicts", "sum"),
            sequencing_violations=("sequencing_violations", "sum"),
        )
        .reset_index(drop=True)
    )
    aggregated["utilisation_ratio"] = aggregated.apply(
        lambda row: row["total_hours"] / row["available_hours"]
        if row["available_hours"] > 0
        else None,
        axis=1,
    )
    return aggregated
