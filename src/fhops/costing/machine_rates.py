"""Machine rate loader for OpCost-style costing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from functools import lru_cache
from typing import Sequence

DATA_PATH = Path(__file__).resolve().parents[3] / "data/machine_rates.json"


@dataclass(frozen=True)
class MachineRate:
    machine_name: str
    role: str
    ownership_cost_per_smh: float
    operating_cost_per_smh: float
    default_utilization: float
    move_in_cost: float
    source: str
    notes: str | None = None
    repair_maintenance_cost_per_smh: float | None = None
    repair_maintenance_reference_hours: int | None = None
    repair_maintenance_usage_multipliers: dict[int, float] | None = None

    @property
    def total_cost_per_smh(self) -> float:
        return self.ownership_cost_per_smh + self.operating_cost_per_smh


def load_default_machine_rates() -> Sequence[MachineRate]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing machine rate data: {DATA_PATH}")
    with DATA_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    rates = []
    for entry in data:
        rates.append(
            MachineRate(
                machine_name=entry["machine_name"],
                role=entry["role"],
                ownership_cost_per_smh=float(entry["ownership_cost_per_smh"]),
                operating_cost_per_smh=float(entry["operating_cost_per_smh"]),
                default_utilization=float(entry["default_utilization"]),
                move_in_cost=float(entry.get("move_in_cost", 0.0)),
                source=entry.get("source", ""),
                notes=entry.get("notes"),
                repair_maintenance_cost_per_smh=(
                    float(entry["repair_maintenance_cost_per_smh"])
                    if entry.get("repair_maintenance_cost_per_smh") is not None
                    else None
                ),
                repair_maintenance_reference_hours=(
                    int(entry["repair_maintenance_reference_hours"])
                    if entry.get("repair_maintenance_reference_hours") is not None
                    else None
                ),
                repair_maintenance_usage_multipliers=(
                    {int(k): float(v) for k, v in entry["repair_maintenance_usage_multipliers"].items()}
                    if entry.get("repair_maintenance_usage_multipliers") is not None
                    else None
                ),
            )
        )
    return tuple(rates)


ROLE_SYNONYMS = {
    "roadside_processor": "processor",
    "landing_processor_or_hand_buck": "processor",
    "hand_buck_or_processor": "processor",
    "loader_or_water": "loader",
}


def normalize_machine_role(role: str | None) -> str | None:
    if role is None:
        return None
    stripped = role.strip().lower()
    if not stripped:
        return None
    slug = re.sub(r"[^\w]+", "_", stripped).strip("_")
    if not slug:
        return None
    return ROLE_SYNONYMS.get(slug, slug)


@lru_cache(maxsize=1)
def load_machine_rate_index() -> dict[str, MachineRate]:
    """Return a cached mapping of normalised role → machine rate."""

    index: dict[str, MachineRate] = {}
    for rate in load_default_machine_rates():
        key = normalize_machine_role(rate.role) or rate.role
        index[key] = rate
    return index


def get_machine_rate(role: str) -> MachineRate | None:
    """Return the default machine rate entry for the supplied role (case-insensitive)."""

    normalised = normalize_machine_role(role)
    if normalised is None:
        return None
    return load_machine_rate_index().get(normalised)


def select_usage_class_multiplier(
    machine_rate: MachineRate, usage_hours: int | None
) -> tuple[int, float] | None:
    """
    Return the (usage_hours_bucket, multiplier) pair closest to the requested usage.

    Buckets come from FPInnovations Advantage Vol. 4 No. 23 Table 2 (5k-hour increments).
    """

    if usage_hours is None:
        return None
    mapping = machine_rate.repair_maintenance_usage_multipliers
    if not mapping:
        return None
    bucket, multiplier = min(
        mapping.items(),
        key=lambda item: (abs(usage_hours - item[0]), item[0]),
    )
    return bucket, multiplier


def compose_rental_rate(
    machine_rate: MachineRate,
    *,
    include_repair_maintenance: bool = True,
    ownership_override: float | None = None,
    operating_override: float | None = None,
    repair_override: float | None = None,
    usage_hours: int | None = None,
) -> tuple[float, dict[str, float]]:
    """
    Return the rental rate ($/SMH) and component breakdown for a machine.

    Parameters
    ----------
    machine_rate:
        Source machine rate entry (owning + operating + optional repair/maintenance).
    include_repair_maintenance:
        Whether to include the repair/maintenance allowance from FPInnovations (default True).
    ownership_override, operating_override, repair_override:
        Optional values that replace the corresponding component before totals are computed.
    """

    ownership = ownership_override if ownership_override is not None else machine_rate.ownership_cost_per_smh
    operating = operating_override if operating_override is not None else machine_rate.operating_cost_per_smh

    repair_candidate: float = 0.0
    if repair_override is not None:
        repair_candidate = repair_override
    elif machine_rate.repair_maintenance_cost_per_smh is not None:
        repair_candidate = machine_rate.repair_maintenance_cost_per_smh
        if usage_hours is not None:
            selection = select_usage_class_multiplier(machine_rate, usage_hours)
            if selection is not None:
                _, multiplier = selection
                repair_candidate *= multiplier
    repair = repair_candidate if include_repair_maintenance else 0.0

    breakdown: dict[str, float] = {
        "ownership": ownership,
        "operating": operating,
    }
    if repair > 0:
        breakdown["repair_maintenance"] = repair

    total = ownership + operating + repair
    return total, breakdown


def compose_default_rental_rate_for_role(
    role: str,
    *,
    include_repair_maintenance: bool = True,
    ownership_override: float | None = None,
    operating_override: float | None = None,
    repair_override: float | None = None,
    usage_hours: int | None = None,
) -> tuple[float, dict[str, float]] | None:
    """Compose the rental rate for a machine role directly from the defaults."""

    rate = get_machine_rate(role)
    if rate is None:
        return None
    return compose_rental_rate(
        rate,
        include_repair_maintenance=include_repair_maintenance,
        ownership_override=ownership_override,
        operating_override=operating_override,
        repair_override=repair_override,
        usage_hours=usage_hours,
    )


__all__ = [
    "MachineRate",
    "load_default_machine_rates",
    "load_machine_rate_index",
    "get_machine_rate",
    "select_usage_class_multiplier",
    "compose_rental_rate",
    "compose_default_rental_rate_for_role",
    "normalize_machine_role",
]
