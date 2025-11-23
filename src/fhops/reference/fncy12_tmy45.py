"""Loader for FNCY12/TN258 Thunderbird TMY45 + Mini-Mak II dataset."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/fncy12_tmy45_mini_mak.json"
)


@dataclass(frozen=True)
class Fncy12MonthlyProductivity:
    month: str
    volume_m3: float | None
    productive_shifts: float | None
    avg_shift_m3: float | None


@dataclass(frozen=True)
class Fncy12Dataset:
    source: Mapping[str, Any]
    operation: Mapping[str, Any]
    intermediate_supports: Mapping[str, Any]
    productivity_months: Sequence[Fncy12MonthlyProductivity]
    productivity_totals: Mapping[str, Any]
    shift_hours: float
    lateral_limit_m: float | None
    max_skyline_tension_kn: float | None
    max_guyline_tension_kn: float | None
    support_cat_d8_ratio: float | None
    support_timberjack_ratio: float | None
    support_monthly_summary: Mapping[str, Any] | None


def _parse_month(entry: Mapping[str, Any]) -> Fncy12MonthlyProductivity:
    return Fncy12MonthlyProductivity(
        month=str(entry.get("month", "")),
        volume_m3=entry.get("volume_m3"),
        productive_shifts=entry.get("productive_shifts"),
        avg_shift_m3=entry.get("avg_shift_m3"),
    )


def _max_tension(entries: Sequence[Mapping[str, Any]]) -> float | None:
    max_value: float | None = None
    for entry in entries:
        for key in (
            "empty_carriage",
            "breakout",
            "lateral_yarding",
            "suspended_under_carriage",
            "over_intermediate_support",
            "between_support_and_yarder",
        ):
            value = entry.get(key)
            if isinstance(value, int | float):
                max_value = value if max_value is None else max(max_value, float(value))
    return max_value


def _support_ratio(payload: Mapping[str, Any], key: str) -> float | None:
    section = payload.get("support_cost_proxies", {}).get(key)
    if not isinstance(section, Mapping):
        return None
    value = section.get("assumed_ratio_support_smh_per_yarder_smh")
    return float(value) if isinstance(value, int | float) else None


@lru_cache(maxsize=1)
def load_fncy12_dataset() -> Fncy12Dataset:
    if not _DATA_PATH.exists():  # pragma: no cover - validates repo layout
        raise FileNotFoundError(f"FNCY12 dataset missing: {_DATA_PATH}")
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    productivity = payload.get("productivity", {})
    months = tuple(
        _parse_month(entry)
        for entry in productivity.get("volumes_m3_per_month", [])
        if isinstance(entry, Mapping)
    )
    totals = productivity.get("totals", {})
    shift_hours = productivity.get("shift_hours")
    shift_hours_value = float(shift_hours) if isinstance(shift_hours, int | float) else 10.0
    intermediate_supports = payload.get("intermediate_supports", {}) or {}
    operation = payload.get("operation", {}) or {}
    lateral_limit = intermediate_supports.get("lateral_limit_m") or operation.get(
        "lateral_yarding_limit_m"
    )
    lateral_limit_value = float(lateral_limit) if isinstance(lateral_limit, int | float) else None
    tension_observations = payload.get("tension_observations", {})
    skyline_entries = tension_observations.get("skyline_kN", []) if tension_observations else []
    guyline_entries = tension_observations.get("guyline_kN", []) if tension_observations else []
    max_skyline = _max_tension(skyline_entries) if skyline_entries else None
    max_guyline = _max_tension(guyline_entries) if guyline_entries else None
    return Fncy12Dataset(
        source=payload.get("source", {}),
        operation=operation,
        intermediate_supports=intermediate_supports,
        productivity_months=months,
        productivity_totals=totals,
        shift_hours=shift_hours_value,
        lateral_limit_m=lateral_limit_value,
        max_skyline_tension_kn=max_skyline,
        max_guyline_tension_kn=max_guyline,
        support_cat_d8_ratio=_support_ratio(payload, "cat_d8_backspar"),
        support_timberjack_ratio=_support_ratio(payload, "timberjack_450_trail_support"),
        support_monthly_summary=payload.get("support_monthly_summary"),
    )


__all__ = ["Fncy12Dataset", "Fncy12MonthlyProductivity", "load_fncy12_dataset"]
