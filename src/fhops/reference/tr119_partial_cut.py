"""Load TR119 partial-cut yarding productivity/cost data."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = (
    Path(__file__).resolve().parents[3]
    / "notes/reference/fpinnovations/tr119_yarding_productivity.json"
)


@dataclass(frozen=True)
class Tr119Treatment:
    treatment: str
    volume_multiplier: float
    yarding_equipment_cost_per_m3: float | None
    yarding_labour_cost_per_m3: float | None
    yarding_total_cost_per_m3: float | None


@lru_cache(maxsize=1)
def load_tr119_treatments() -> Sequence[Tr119Treatment]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing TR119 dataset: {DATA_PATH}")
    with DATA_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return tuple(
        Tr119Treatment(
            treatment=entry["treatment"],
            volume_multiplier=float(entry.get("volume_multiplier", 1.0)),
            yarding_equipment_cost_per_m3=_maybe_float(entry.get("yarding_equipment_cost_per_m3")),
            yarding_labour_cost_per_m3=_maybe_float(entry.get("yarding_labour_cost_per_m3")),
            yarding_total_cost_per_m3=_maybe_float(entry.get("yarding_total_cost_per_m3")),
        )
        for entry in payload
    )


def _maybe_float(value):
    if value is None:
        return None
    return float(value)


def get_tr119_treatment(treatment: str) -> Tr119Treatment:
    normalized = treatment.strip().lower()
    for entry in load_tr119_treatments():
        if entry.treatment.lower() == normalized:
            return entry
    raise KeyError(f"TR119 treatment '{treatment}' not found")


__all__ = ["Tr119Treatment", "load_tr119_treatments", "get_tr119_treatment"]
