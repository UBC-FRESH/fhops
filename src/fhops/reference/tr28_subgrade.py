"""Helpers for FERIC TR-28 subgrade machine metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

_DATA_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tr28_subgrade_machines.json"
)


@dataclass(frozen=True)
class TR28Machine:
    """Structured view of the TR-28 machine rows we care about."""

    case_id: int | None
    machine_name: str
    role: str
    working_cycle_minutes: float | None
    walking_speed_kmh: float | None
    excavation_rate_m3_per_hr: float | None
    station_cost_cad: float | None
    unit_cost_cad_per_meter: float | None
    stations_per_shift: float | None
    meters_per_shift: float | None
    machine_hourly_rate_cad: float | None
    subgrading_cost_cad: float | None
    total_subgrade_cost_cad: float | None
    movement_machine_hours: float | None
    movement_total_cost_cad: float | None
    roughness_m2_per_100m: float | None
    raw: Mapping[str, Any]


@lru_cache(maxsize=1)
def load_tr28_machines() -> Sequence[TR28Machine]:
    """Load and cache the TR-28 machine entries."""

    if not _DATA_PATH.exists():
        raise FileNotFoundError(f"TR-28 dataset missing: {_DATA_PATH}")
    with _DATA_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    machines: list[TR28Machine] = []
    for entry in payload.get("machines", []):
        movement = entry.get("movement") or {}
        costs = entry.get("costs") or {}
        shift = entry.get("shift_production") or {}
        machine = TR28Machine(
            case_id=entry.get("case_id"),
            machine_name=entry.get("machine_name", "Unknown"),
            role=entry.get("role", ""),
            working_cycle_minutes=entry.get("working_speed_minutes"),
            walking_speed_kmh=entry.get("walking_speed_kmh"),
            excavation_rate_m3_per_hr=entry.get("excavation_rate_m3_per_hr"),
            station_cost_cad=costs.get("station_cost_cad"),
            unit_cost_cad_per_meter=costs.get("unit_cost_cad_per_meter"),
            stations_per_shift=shift.get("stations_per_shift"),
            meters_per_shift=shift.get("meters_per_shift"),
            machine_hourly_rate_cad=entry.get("machine_hourly_rate_cad"),
            subgrading_cost_cad=costs.get("subgrading_cost_cad"),
            total_subgrade_cost_cad=costs.get("total_subgrade_cost_cad"),
            movement_machine_hours=movement.get("machine_hours"),
            movement_total_cost_cad=movement.get("total_move_cost_cad"),
            roughness_m2_per_100m=(entry.get("roughness_indicator") or {}).get("m2_per_100m"),
            raw=entry,
        )
        machines.append(machine)
    return tuple(machines)


@lru_cache(maxsize=1)
def get_tr28_source_metadata() -> Mapping[str, Any]:
    """Return the top-level TR-28 metadata block."""

    if not _DATA_PATH.exists():
        raise FileNotFoundError(f"TR-28 dataset missing: {_DATA_PATH}")
    with _DATA_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload.get("source", {})


__all__ = ["TR28Machine", "load_tr28_machines", "get_tr28_source_metadata"]
