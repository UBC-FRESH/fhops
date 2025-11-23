"""Helpers for capturing machine cost snapshots for telemetry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fhops.costing.machine_rates import (
    MachineRate,
    compose_default_rental_rate_for_role,
    get_machine_rate,
    select_usage_class_multiplier,
)


@dataclass(frozen=True)
class MachineCostSnapshot:
    """
    CPI-adjusted snapshot of a machine's cost profile for telemetry logging.

    Attributes
    ----------
    machine_id:
        Identifier taken from :class:`fhops.scenario.contract.models.Machine`.
    role:
        Normalised machine-role slug (e.g., ``forwarder``) used for rate lookups.
    operating_cost:
        Per-shift operating cost if the scenario explicitly specifies one (CAD/SMH).
    repair_usage_hours:
        Optional cumulative SMH used to select repair/maintenance multipliers.
    rental_rate_smh:
        Composed rental rate ($/SMH) calculated via
        :func:`fhops.costing.machine_rates.compose_default_rental_rate_for_role`.
    ownership, operating, repair_maintenance:
        Individual rental-rate components ($/SMH). ``repair_maintenance`` is ``None`` when the
        reference rate lacks data or the CLI omits the component.
    usage_bucket_hours, usage_multiplier:
        Advantage Vol. 4 No. 23 usage bucket and multiplier (if the machine rate defines one).
    cost_base_year:
        Original CPI base year for the rate card; populated from the machine payload or the default
        rate entry.
    """

    machine_id: str
    role: str | None
    operating_cost: float | None
    repair_usage_hours: int | None
    rental_rate_smh: float | None = None
    ownership: float | None = None
    operating: float | None = None
    repair_maintenance: float | None = None
    usage_bucket_hours: int | None = None
    usage_multiplier: float | None = None
    cost_base_year: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the snapshot into a JSON-serialisable dictionary.

        Returns
        -------
        dict[str, Any]
            Mapping of all attributes suitable for telemetry JSONL entries.
        """

        return {
            "machine_id": self.machine_id,
            "role": self.role,
            "operating_cost": self.operating_cost,
            "repair_usage_hours": self.repair_usage_hours,
            "rental_rate_smh": self.rental_rate_smh,
            "ownership": self.ownership,
            "operating": self.operating,
            "repair_maintenance": self.repair_maintenance,
            "usage_bucket_hours": self.usage_bucket_hours,
            "usage_multiplier": self.usage_multiplier,
            "cost_base_year": self.cost_base_year,
        }


def build_machine_cost_snapshots(machines: Iterable[Any]) -> list[MachineCostSnapshot]:
    """
    Materialise machine-cost snapshots for every machine in a scenario.

    Parameters
    ----------
    machines:
        Iterable of ``Machine`` model instances (or objects exposing ``id``/``role``/cost fields).

    Returns
    -------
    list[MachineCostSnapshot]
        CPI-adjusted cost records for telemetry logging and CLI summaries. Entries lacking machine
        IDs are skipped.
    """

    snapshots: list[MachineCostSnapshot] = []
    for machine in machines:
        machine_id = getattr(machine, "id", None)
        if machine_id is None:
            continue
        role = getattr(machine, "role", None)
        operating_cost = (
            float(getattr(machine, "operating_cost", 0.0))
            if hasattr(machine, "operating_cost")
            else None
        )
        repair_usage_hours = getattr(machine, "repair_usage_hours", None)

        rental_rate = None
        ownership = None
        operating = None
        repair = None
        usage_bucket_hours = None
        usage_multiplier = None

        cost_base_year = getattr(machine, "cost_base_year", None)
        if role:
            composed = compose_default_rental_rate_for_role(role, usage_hours=repair_usage_hours)
            if composed is not None:
                rental_rate, breakdown = composed
                ownership = breakdown["ownership"]
                operating = breakdown["operating"]
                repair = breakdown.get("repair_maintenance")

                rate_entry: MachineRate | None = get_machine_rate(role)
                if rate_entry and repair_usage_hours is not None:
                    bucket = select_usage_class_multiplier(rate_entry, repair_usage_hours)
                    if bucket is not None:
                        usage_bucket_hours, usage_multiplier = bucket
                if rate_entry and cost_base_year is None:
                    cost_base_year = rate_entry.cost_base_year

        snapshots.append(
            MachineCostSnapshot(
                machine_id=machine_id,
                role=role,
                operating_cost=operating_cost,
                repair_usage_hours=repair_usage_hours,
                rental_rate_smh=rental_rate,
                ownership=ownership,
                operating=operating,
                repair_maintenance=repair,
                usage_bucket_hours=usage_bucket_hours,
                usage_multiplier=usage_multiplier,
                cost_base_year=cost_base_year,
            )
        )
    return snapshots


def summarize_machine_costs(machine_costs: object) -> str:
    """
    Generate a concise string summarising one or more machine cost entries.

    Parameters
    ----------
    machine_costs:
        List of dictionaries (such as :meth:`MachineCostSnapshot.to_dict`). Non-list values are
        ignored.

    Returns
    -------
    str
        Pipe-delimited fragments (``role: own=..., op=..., rep=...``) ready for telemetry tables.
    """

    if not isinstance(machine_costs, list):
        return ""

    fragments: list[str] = []
    for entry in machine_costs:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role") or entry.get("machine_id") or "unknown"
        ownership = entry.get("ownership")
        operating = entry.get("operating")
        repair = entry.get("repair_maintenance")
        usage = entry.get("usage_bucket_hours") or entry.get("repair_usage_hours")
        parts: list[str] = []
        if ownership is not None:
            parts.append(f"own={ownership}")
        if operating is not None:
            parts.append(f"op={operating}")
        if repair is not None:
            parts.append(f"rep={repair}")
        if usage is not None:
            parts.append(f"usage={usage:,}h")
        base_year = entry.get("cost_base_year")
        if base_year:
            parts.append(f"base={base_year} CAD")
        if not parts:
            continue
        fragments.append(f"{role}: " + ", ".join(parts))
    return " | ".join(fragments)


__all__ = ["MachineCostSnapshot", "build_machine_cost_snapshots", "summarize_machine_costs"]
