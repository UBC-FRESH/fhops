"""Helpers for FERIC TR-28 subgrade machine metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

_DATA_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tr28_subgrade_machines.json"
)
_STATION_LENGTH_M = 30.48


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "tr28_machine"


@dataclass(frozen=True)
class TR28Machine:
    """Structured view of the TR-28 machine rows we care about."""

    slug: str
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


@dataclass(frozen=True)
class TR28CostEstimate:
    """Cost estimate for a TR-28 machine over a specified road length."""

    machine: TR28Machine
    road_length_m: float
    stations: float
    shifts: float | None
    unit_cost_base_cad_per_m: float
    unit_cost_target_cad_per_m: float
    total_cost_base_cad: float
    total_cost_target_cad: float
    mobilisation_included: bool
    mobilisation_cost_base_cad: float
    mobilisation_cost_target_cad: float
    total_with_mobilisation_base_cad: float
    total_with_mobilisation_target_cad: float
    base_year: int
    target_year: int


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
            slug=entry.get("slug") or _slugify(entry.get("machine_name", "")),
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


@lru_cache(maxsize=1)
def tr28_currency_year() -> int:
    """Parse the base currency year from the TR-28 metadata."""

    source = get_tr28_source_metadata()
    currency = source.get("currency", "")
    if isinstance(currency, str) and "_" in currency:
        _, _, maybe_year = currency.rpartition("_")
        if maybe_year.isdigit():
            return int(maybe_year)
    year = source.get("currency_year")
    if isinstance(year, int):
        return year
    # Default to the publication's stated CAD_1976 if nothing else surfaces.
    return 1976


def estimate_tr28_road_cost(
    machine: TR28Machine,
    road_length_m: float,
    *,
    include_mobilisation: bool = True,
    target_year: int | None = None,
) -> TR28CostEstimate:
    """Estimate CPI-adjusted subgrade cost for a TR-28 machine over ``road_length_m``."""

    from fhops.costing.inflation import TARGET_YEAR, inflate_value

    if road_length_m <= 0:
        raise ValueError("road_length_m must be > 0.")
    unit_cost = machine.unit_cost_cad_per_meter
    if unit_cost is None and machine.station_cost_cad is not None:
        unit_cost = machine.station_cost_cad / _STATION_LENGTH_M
    if unit_cost is None:
        raise ValueError(
            f"Machine '{machine.machine_name}' is missing unit cost information in TR-28 dataset."
        )
    resolved_target_year = target_year or TARGET_YEAR
    base_year = tr28_currency_year()
    stations = road_length_m / _STATION_LENGTH_M
    total_base = unit_cost * road_length_m
    mobilisation_base = machine.movement_total_cost_cad or 0.0
    mobilisation_used_base = mobilisation_base if include_mobilisation else 0.0
    total_with_mob_base = total_base + mobilisation_used_base
    unit_target = inflate_value(unit_cost, base_year, resolved_target_year) or 0.0
    total_target = unit_target * road_length_m
    mobilisation_target = (
        inflate_value(mobilisation_used_base, base_year, resolved_target_year) or 0.0
    )
    total_with_mob_target = total_target + mobilisation_target
    shifts = None
    if machine.meters_per_shift:
        shifts = road_length_m / machine.meters_per_shift
    return TR28CostEstimate(
        machine=machine,
        road_length_m=road_length_m,
        stations=stations,
        shifts=shifts,
        unit_cost_base_cad_per_m=unit_cost,
        unit_cost_target_cad_per_m=unit_target,
        total_cost_base_cad=total_base,
        total_cost_target_cad=total_target,
        mobilisation_included=include_mobilisation,
        mobilisation_cost_base_cad=mobilisation_used_base,
        mobilisation_cost_target_cad=mobilisation_target,
        total_with_mobilisation_base_cad=total_with_mob_base,
        total_with_mobilisation_target_cad=total_with_mob_target,
        base_year=base_year,
        target_year=resolved_target_year,
    )


__all__ = [
    "TR28Machine",
    "TR28CostEstimate",
    "estimate_tr28_road_cost",
    "get_tr28_source_metadata",
    "load_tr28_machines",
    "tr28_currency_year",
]
