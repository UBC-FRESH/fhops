"""Loader for the TN98 handfalling productivity/cost dataset."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tn98_handfalling.json"
)


@dataclass(frozen=True)
class TN98Regression:
    sample_size: int
    r_squared: float | None
    std_error_minutes: float | None
    intercept_minutes: float
    slope_minutes_per_cm: float


@dataclass(frozen=True)
class TN98DiameterRecord:
    dbh_cm: float
    tree_count: int | None
    cut_minutes: float | None
    limb_buck_minutes: float | None
    volume_m3: float | None
    cost_per_tree_cad: float | None
    cost_per_m3_cad: float | None


@dataclass(frozen=True)
class TN98HandfallingDataset:
    source: Mapping[str, Any]
    site: Mapping[str, Any]
    labour_costs: Mapping[str, Any]
    time_distribution: Mapping[str, Any]
    summary_productivity: Mapping[str, Any]
    diameter_classes_cm: Sequence[float]
    regressions: Mapping[str, TN98Regression]
    per_diameter_class: Mapping[str, Sequence[TN98DiameterRecord]]


def _load_raw_payload() -> Mapping[str, Any]:
    if not _DATA_PATH.exists():
        raise FileNotFoundError(f"TN98 dataset missing: {_DATA_PATH}")
    with _DATA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _parse_regressions(payload: Mapping[str, Any]) -> Mapping[str, TN98Regression]:
    regressions = {}
    raw = payload.get("cutting_time_regressions", {})
    for key, value in raw.items():
        regressions[key] = TN98Regression(
            sample_size=value.get("sample_size", 0),
            r_squared=value.get("r_squared"),
            std_error_minutes=value.get("std_error_minutes"),
            intercept_minutes=value.get("intercept_minutes", 0.0),
            slope_minutes_per_cm=value.get("slope_minutes_per_cm", 0.0),
        )
    return regressions


def _parse_diameter_records(
    payload: Mapping[str, Any],
) -> Mapping[str, Sequence[TN98DiameterRecord]]:
    result: dict[str, tuple[TN98DiameterRecord, ...]] = {}
    raw = payload.get("per_diameter_class", {})
    for species, entries in raw.items():
        parsed: list[TN98DiameterRecord] = []
        for entry in entries:
            parsed.append(
                TN98DiameterRecord(
                    dbh_cm=entry.get("dbh_cm", 0.0),
                    tree_count=entry.get("tree_count"),
                    cut_minutes=entry.get("cut_minutes"),
                    limb_buck_minutes=entry.get("limb_buck_minutes"),
                    volume_m3=entry.get("volume_m3"),
                    cost_per_tree_cad=entry.get("cost_per_tree_cad"),
                    cost_per_m3_cad=entry.get("cost_per_m3_cad"),
                )
            )
        result[species] = tuple(sorted(parsed, key=lambda rec: rec.dbh_cm))
    return result


@lru_cache(maxsize=1)
def load_tn98_dataset() -> TN98HandfallingDataset:
    payload = _load_raw_payload()
    regressions = _parse_regressions(payload)
    records = _parse_diameter_records(payload)
    return TN98HandfallingDataset(
        source=payload.get("source", {}),
        site=payload.get("site", {}),
        labour_costs=payload.get("labour_costs", {}),
        time_distribution=payload.get("time_distribution", {}),
        summary_productivity=payload.get("summary_productivity", {}),
        diameter_classes_cm=tuple(payload.get("diameter_classes_cm", [])),
        regressions=regressions,
        per_diameter_class=records,
    )


__all__ = ["TN98HandfallingDataset", "TN98Regression", "TN98DiameterRecord", "load_tn98_dataset"]
