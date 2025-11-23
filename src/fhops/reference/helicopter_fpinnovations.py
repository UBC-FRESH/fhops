"""Loader for aggregated FPInnovations helicopter datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:  # pragma: no cover - import-time typing helper
    from fhops.productivity.cable_logging import HelicopterLonglineModel

_DATA_PATH = Path(__file__).resolve().parents[3] / "data/productivity/helicopter_fpinnovations.json"


@dataclass(frozen=True)
class HelicopterSource:
    """Metadata describing the originating FPInnovations publication."""

    source_id: str
    title: str
    publication_date: str | None = None
    publisher: str | None = None
    currency: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class HelicopterOperation:
    """Structured productivity/cost record for a helicopter configuration."""

    id: str
    source_id: str
    helicopter_model: "HelicopterLonglineModel"
    configuration: str
    lift_class: str | None
    treatment: str | None
    flight_hours_per_shift: float | None
    average_flight_distance_m: float | None
    productivity_m3_per_shift: float | None
    productivity_m3_per_flight_hour: float | None
    turns_per_flight_hour: float | None
    turn_time_minutes: float | None
    payload_kg_per_turn: float | None
    payload_m3_per_turn: float | None
    load_factor: float | None
    weight_to_volume_lb_per_m3: float | None
    turn_breakdown_minutes: Mapping[str, float] | None
    additional_delay_minutes: float | None
    cost_per_m3_cad: float | None
    hourly_cost_cad: float | None
    cost_base_year: int | None
    abort_rate_percent: float | None
    notes: str | None = None


@dataclass(frozen=True)
class HelicopterFPInnovationsDataset:
    """Container for the helicopter dataset plus helper lookup tables."""

    sources: Mapping[str, HelicopterSource]
    defaults: Mapping["HelicopterLonglineModel", str]
    operations: tuple[HelicopterOperation, ...]
    operation_index: Mapping[str, HelicopterOperation]


def _coerce_model(value: str) -> HelicopterLonglineModel:
    from fhops.productivity.cable_logging import HelicopterLonglineModel

    try:
        return HelicopterLonglineModel(value)
    except ValueError as exc:  # pragma: no cover - invalid dataset entries
        raise ValueError(f"Unknown helicopter model '{value}' in dataset.") from exc


def _parse_source(source_id: str, payload: Mapping[str, Any]) -> HelicopterSource:
    return HelicopterSource(
        source_id=source_id,
        title=str(payload.get("title", "")).strip(),
        publication_date=payload.get("publication_date"),
        publisher=payload.get("publisher"),
        currency=payload.get("currency"),
        notes=payload.get("notes"),
    )


def _parse_operation(entry: Mapping[str, Any]) -> HelicopterOperation:
    model = _coerce_model(entry["helicopter_model"])
    breakdown = entry.get("turn_breakdown_minutes")
    parsed_breakdown: Mapping[str, float] | None = None
    if isinstance(breakdown, Mapping):
        parsed_breakdown = {str(k): float(v) for k, v in breakdown.items()}
    additional_delay = entry.get("additional_delay_minutes")
    cost_base_year = entry.get("cost_base_year")
    return HelicopterOperation(
        id=str(entry["id"]),
        source_id=str(entry["source_id"]),
        helicopter_model=model,
        configuration=entry.get("configuration", ""),
        lift_class=entry.get("lift_class"),
        treatment=entry.get("treatment"),
        flight_hours_per_shift=_maybe_float(entry.get("flight_hours_per_shift")),
        average_flight_distance_m=_maybe_float(entry.get("average_flight_distance_m")),
        productivity_m3_per_shift=_maybe_float(entry.get("productivity_m3_per_shift")),
        productivity_m3_per_flight_hour=_maybe_float(entry.get("productivity_m3_per_flight_hour")),
        turns_per_flight_hour=_maybe_float(entry.get("turns_per_flight_hour")),
        turn_time_minutes=_maybe_float(entry.get("turn_time_minutes")),
        payload_kg_per_turn=_maybe_float(entry.get("payload_kg_per_turn")),
        payload_m3_per_turn=_maybe_float(entry.get("payload_m3_per_turn")),
        load_factor=_maybe_float(entry.get("load_factor")),
        weight_to_volume_lb_per_m3=_maybe_float(entry.get("weight_to_volume_lb_per_m3")),
        turn_breakdown_minutes=parsed_breakdown,
        additional_delay_minutes=_maybe_float(additional_delay),
        cost_per_m3_cad=_maybe_float(entry.get("cost_per_m3_cad")),
        hourly_cost_cad=_maybe_float(entry.get("hourly_cost_cad")),
        cost_base_year=int(cost_base_year) if cost_base_year is not None else None,
        abort_rate_percent=_maybe_float(entry.get("abort_rate_percent")),
        notes=entry.get("notes"),
    )


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - invalid dataset entries
        raise ValueError(f"Expected a numeric value, got {value!r}.")


@lru_cache(maxsize=1)
def load_helicopter_fpinnovations_dataset() -> HelicopterFPInnovationsDataset:
    if not _DATA_PATH.exists():
        raise FileNotFoundError(f"Missing helicopter dataset: {_DATA_PATH}")
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    sources_payload = payload.get("sources", {})
    sources = {
        source_id: _parse_source(source_id, source_payload)
        for source_id, source_payload in sources_payload.items()
    }
    operations_payload = payload.get("operations", [])
    operations: list[HelicopterOperation] = []
    operation_index: dict[str, HelicopterOperation] = {}
    for entry in operations_payload:
        op = _parse_operation(entry)
        operations.append(op)
        operation_index[op.id] = op
    defaults_payload = payload.get("defaults", {})
    defaults: dict[HelicopterLonglineModel, str] = {}
    for model_slug, op_id in defaults_payload.items():
        try:
            model = _coerce_model(model_slug)
        except ValueError:
            continue
        defaults[model] = str(op_id)
    return HelicopterFPInnovationsDataset(
        sources=sources,
        defaults=defaults,
        operations=tuple(operations),
        operation_index=operation_index,
    )


def get_helicopter_operation(operation_id: str) -> HelicopterOperation:
    dataset = load_helicopter_fpinnovations_dataset()
    try:
        return dataset.operation_index[operation_id]
    except KeyError as exc:
        raise KeyError(f"Unknown helicopter operation '{operation_id}'.") from exc


def get_default_helicopter_operation(
    model: HelicopterLonglineModel,
) -> HelicopterOperation | None:
    dataset = load_helicopter_fpinnovations_dataset()
    op_id = dataset.defaults.get(model)
    if op_id is None:
        return None
    return dataset.operation_index.get(op_id)


__all__ = [
    "HelicopterFPInnovationsDataset",
    "HelicopterOperation",
    "HelicopterSource",
    "get_default_helicopter_operation",
    "get_helicopter_operation",
    "load_helicopter_fpinnovations_dataset",
]
