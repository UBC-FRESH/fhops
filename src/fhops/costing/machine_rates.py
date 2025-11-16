"""Machine rate loader for OpCost-style costing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
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
            )
        )
    return tuple(rates)


def compose_rental_rate(
    machine_rate: MachineRate,
    *,
    include_repair_maintenance: bool = True,
    ownership_override: float | None = None,
    operating_override: float | None = None,
    repair_override: float | None = None,
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
    repair = repair_candidate if include_repair_maintenance else 0.0

    breakdown: dict[str, float] = {
        "ownership": ownership,
        "operating": operating,
    }
    if repair > 0:
        breakdown["repair_maintenance"] = repair

    total = ownership + operating + repair
    return total, breakdown


__all__ = ["MachineRate", "load_default_machine_rates", "compose_rental_rate"]
