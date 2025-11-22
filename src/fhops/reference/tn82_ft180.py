"""Loader for the TN82 FMC FT-180 vs. John Deere 550 dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

_DATA_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tn82_ft180_jd550.json"
)


@dataclass(frozen=True)
class TN82AreaSummary:
    site_id: str
    productive_hours_percent: float | None
    availability_percent: float | None
    volume_m3_per_pmh: float
    trees_per_pmh: float
    turns_per_pmh: float
    volume_m3_per_shift: float
    trees_per_shift: float
    turns_per_shift: float


@dataclass(frozen=True)
class TN82Machine:
    machine_id: str
    name: str
    machine_type: str
    notes: str | None
    areas: Sequence[TN82AreaSummary]


@dataclass(frozen=True)
class TN82Dataset:
    source: Mapping[str, Any]
    sites: Sequence[Mapping[str, Any]]
    machines: Sequence[TN82Machine]
    system_notes: Sequence[str]


def _parse_area(entry: Mapping[str, Any]) -> TN82AreaSummary:
    return TN82AreaSummary(
        site_id=str(entry["site_id"]),
        productive_hours_percent=entry.get("productive_hours_percent"),
        availability_percent=entry.get("availability_percent"),
        volume_m3_per_pmh=float(entry["volume_m3_per_pmh"]),
        trees_per_pmh=float(entry["trees_per_pmh"]),
        turns_per_pmh=float(entry["turns_per_pmh"]),
        volume_m3_per_shift=float(entry["volume_m3_per_shift"]),
        trees_per_shift=float(entry["trees_per_shift"]),
        turns_per_shift=float(entry["turns_per_shift"]),
    )


def _parse_machine(entry: Mapping[str, Any]) -> TN82Machine:
    areas = [_parse_area(area) for area in entry.get("areas", [])]
    return TN82Machine(
        machine_id=str(entry["id"]),
        name=entry.get("name", entry["id"]),
        machine_type=entry.get("type", "unknown"),
        notes=entry.get("notes"),
        areas=tuple(areas),
    )


@lru_cache(maxsize=1)
def load_tn82_dataset() -> TN82Dataset:
    if not _DATA_PATH.exists():
        raise FileNotFoundError(f"TN82 dataset missing: {_DATA_PATH}")
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    machines = tuple(_parse_machine(entry) for entry in payload.get("machines", []))
    return TN82Dataset(
        source=payload.get("source", {}),
        sites=tuple(payload.get("sites", [])),
        machines=machines,
        system_notes=tuple(payload.get("system_notes", [])),
    )


__all__ = ["TN82Dataset", "TN82Machine", "TN82AreaSummary", "load_tn82_dataset"]
