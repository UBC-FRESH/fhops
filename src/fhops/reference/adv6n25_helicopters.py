"""Loader for ADV6N25 helicopter productivity/cost data."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/adv6n25_helicopters.json"
)


@dataclass(frozen=True)
class ADV6N25Helicopter:
    model: str
    rated_payload_lb: float | None
    longline_length_m: float | None
    turn_hook_weight_kg: float | None
    productivity_m3_per_shift: float | None
    flight_hours_per_shift: float | None
    productivity_m3_per_flight_hour: float | None
    volume_logged_m3: float | None
    cost_per_m3_cad: float | None
    hourly_cost_cad: float | None
    yarding_shifts: float | None
    notes: str | None


@dataclass(frozen=True)
class ADV6N25Dataset:
    source: Mapping[str, Any]
    site: Mapping[str, Any]
    phases: Mapping[str, Any]
    helicopters: Sequence[ADV6N25Helicopter]
    total: Mapping[str, Any]
    alternative_scenarios: Sequence[Mapping[str, Any]]


def _parse_helicopter(entry: Mapping[str, Any]) -> ADV6N25Helicopter:
    return ADV6N25Helicopter(
        model=entry.get("model", "unknown"),
        rated_payload_lb=entry.get("rated_payload_lb"),
        longline_length_m=entry.get("longline_length_m"),
        turn_hook_weight_kg=entry.get("turn_hook_weight_kg"),
        productivity_m3_per_shift=entry.get("productivity_m3_per_shift"),
        flight_hours_per_shift=entry.get("flight_hours_per_shift"),
        productivity_m3_per_flight_hour=entry.get("productivity_m3_per_flight_hour"),
        volume_logged_m3=entry.get("volume_logged_m3"),
        cost_per_m3_cad=entry.get("cost_per_m3_cad"),
        hourly_cost_cad=entry.get("hourly_cost_cad"),
        yarding_shifts=entry.get("yarding_shifts"),
        notes=entry.get("notes"),
    )


@lru_cache(maxsize=1)
def load_adv6n25_dataset() -> ADV6N25Dataset:
    if not _DATA_PATH.exists():
        raise FileNotFoundError(f"ADV6N25 dataset missing: {_DATA_PATH}")
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    helicopters = tuple(_parse_helicopter(entry) for entry in payload.get("helicopters", []))
    return ADV6N25Dataset(
        source=payload.get("source", {}),
        site=payload.get("site", {}),
        phases=payload.get("phases", {}),
        helicopters=helicopters,
        total=payload.get("total", {}),
        alternative_scenarios=tuple(payload.get("alternative_scenarios", [])),
    )


__all__ = ["ADV6N25Dataset", "ADV6N25Helicopter", "load_adv6n25_dataset"]
