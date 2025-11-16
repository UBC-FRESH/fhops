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
            )
        )
    return tuple(rates)


__all__ = ["MachineRate", "load_default_machine_rates"]
