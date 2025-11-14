"""Utility functions for deriving KPI metrics from playback summaries."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import pandas as pd

from fhops.scenario.contract import Problem

__all__ = [
    "compute_makespan_metrics",
    "compute_utilisation_metrics",
]


def compute_utilisation_metrics(
    shift_df: pd.DataFrame,
    day_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Compute utilisation KPI metrics from shift/day playback DataFrames."""

    metrics: dict[str, Any] = {}
    if shift_df is not None and not shift_df.empty and "utilisation_ratio" in shift_df.columns:
        util_shift = shift_df["utilisation_ratio"].dropna()
        if not util_shift.empty:
            metrics["utilisation_ratio_mean_shift"] = float(util_shift.mean())
        total_hours = float(shift_df.get("total_hours", pd.Series(dtype=float)).sum())
        total_available = float(shift_df.get("available_hours", pd.Series(dtype=float)).sum())
        if total_available > 0:
            metrics["utilisation_ratio_weighted_shift"] = total_hours / total_available

        if "machine_id" in shift_df.columns:
            per_machine = (
                shift_df.dropna(subset=["utilisation_ratio"])
                .groupby("machine_id")["utilisation_ratio"]
                .mean()
                .dropna()
            )
            if not per_machine.empty:
                metrics["utilisation_ratio_by_machine"] = json.dumps(
                    {
                        machine: round(float(value), 4)
                        for machine, value in sorted(per_machine.items())
                    }
                )

        if "machine_role" in shift_df.columns:
            per_role = (
                shift_df.dropna(subset=["machine_role", "utilisation_ratio"])
                .groupby("machine_role")["utilisation_ratio"]
                .mean()
                .dropna()
            )
            if not per_role.empty:
                metrics["utilisation_ratio_by_role"] = json.dumps(
                    {role: round(float(value), 4) for role, value in sorted(per_role.items())}
                )

    if day_df is not None and not day_df.empty and "utilisation_ratio" in day_df.columns:
        util_day = day_df["utilisation_ratio"].dropna()
        if not util_day.empty:
            metrics["utilisation_ratio_mean_day"] = float(util_day.mean())
        total_hours_day = float(day_df.get("total_hours", pd.Series(dtype=float)).sum())
        total_available_day = float(day_df.get("available_hours", pd.Series(dtype=float)).sum())
        if total_available_day > 0:
            metrics["utilisation_ratio_weighted_day"] = total_hours_day / total_available_day

    return metrics


def compute_makespan_metrics(
    problem: Problem,
    shift_df: pd.DataFrame,
    *,
    fallback_days: Iterable[int] | None = None,
    fallback_shift_keys: Iterable[tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Compute makespan metrics (latest productive day/shift) given playback summaries."""

    metrics: dict[str, Any] = {"makespan_day": 0, "makespan_shift": "N/A"}

    if shift_df is not None and not shift_df.empty:
        active = shift_df[shift_df.get("production_units", 0) > 0].copy()
        if not active.empty:
            shift_order = {
                (shift.day, shift.shift_id): idx for idx, shift in enumerate(problem.shifts)
            }

            def _rank(row: pd.Series) -> tuple[int, float, float]:
                key = (int(row["day"]), str(row["shift_id"]))
                order = shift_order.get(key)
                if order is not None:
                    return (0, float(order), float(row["day"]))
                return (1, float(row["day"]), 0.0)

            active["_rank_tuple"] = active.apply(_rank, axis=1)
            last_row = active.sort_values("_rank_tuple").iloc[-1]
            metrics["makespan_day"] = int(last_row["day"])
            metrics["makespan_shift"] = str(last_row["shift_id"])
            del active["_rank_tuple"]

    if metrics["makespan_day"] == 0 and fallback_days:
        fallback_days = list(fallback_days)
        if fallback_days:
            metrics["makespan_day"] = max(fallback_days)
    if metrics["makespan_shift"] == "N/A" and fallback_shift_keys:
        fallback_shift_keys = list(fallback_shift_keys)
        if fallback_shift_keys:
            day, shift_id = max(fallback_shift_keys)
            metrics["makespan_day"] = max(metrics["makespan_day"], day)
            metrics["makespan_shift"] = str(shift_id)

    return metrics
