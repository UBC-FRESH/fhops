"""Machine rate loader for OpCost-style costing."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fhops.costing.inflation import TARGET_YEAR, inflate_value
DATA_PATH = Path(__file__).resolve().parents[3] / "data/machine_rates.json"


@dataclass(frozen=True)
class MachineRate:
    """
    Canonical machine-rate entry inspired by FPInnovations OpCost worksheets.

    Attributes
    ----------
    machine_name:
        Display name (e.g., "TimberPro 620E Processor").
    role:
        Human-readable machine role prior to normalisation.
    ownership_cost_per_smh, operating_cost_per_smh:
        CPI-adjusted owning/operating components ($/SMH).
    default_utilization:
        Assumed utilisation fraction (0-1) used in simple costing calculators.
    move_in_cost:
        Mobilisation allowance in CAD.
    source:
        Citation or origin for the rate card.
    notes:
        Optional provenance or cautionary text surfaced in the CLI.
    cost_base_year:
        CPI base year used when the record was ingested.
    repair_maintenance_cost_per_smh:
        Optional FPInnovations repair allowance at the reference usage hours.
    repair_maintenance_reference_hours:
        Usage bucket (SMH) for the repair allowance.
    repair_maintenance_usage_multipliers:
        Mapping of usage-hour buckets → multipliers for scaling the repair allowance.
    """

    machine_name: str
    role: str
    ownership_cost_per_smh: float
    operating_cost_per_smh: float
    default_utilization: float
    move_in_cost: float
    source: str
    notes: str | None = None
    cost_base_year: int = TARGET_YEAR
    repair_maintenance_cost_per_smh: float | None = None
    repair_maintenance_reference_hours: int | None = None
    repair_maintenance_usage_multipliers: dict[int, float] | None = None

    @property
    def total_cost_per_smh(self) -> float:
        """float: Convenience accessor returning owning + operating components ($/SMH)."""

        return self.ownership_cost_per_smh + self.operating_cost_per_smh


def load_default_machine_rates() -> Sequence[MachineRate]:
    """
    Load and CPI-adjust the bundled ``data/machine_rates.json`` reference table.

    Returns
    -------
    tuple[MachineRate, ...]
        Machine rates keyed by role names (before normalisation).

    Raises
    ------
    FileNotFoundError
        If the JSON payload is missing (dev installs without ``git lfs`` often cause this).
    """

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing machine rate data: {DATA_PATH}")
    with DATA_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    rates = []
    for entry in data:
        base_year = int(entry.get("cost_base_year", TARGET_YEAR))

        def adjust(value: float | int | None) -> float:
            if value is None:
                return 0.0
            return float(inflate_value(float(value), base_year))

        rates.append(
            MachineRate(
                machine_name=entry["machine_name"],
                role=entry["role"],
                ownership_cost_per_smh=adjust(entry["ownership_cost_per_smh"]),
                operating_cost_per_smh=adjust(entry["operating_cost_per_smh"]),
                default_utilization=float(entry["default_utilization"]),
                move_in_cost=adjust(entry.get("move_in_cost", 0.0)),
                source=entry.get("source", ""),
                notes=entry.get("notes"),
                cost_base_year=base_year,
                repair_maintenance_cost_per_smh=(
                    float(inflate_value(entry["repair_maintenance_cost_per_smh"], base_year))
                    if entry.get("repair_maintenance_cost_per_smh") is not None
                    else None
                ),
                repair_maintenance_reference_hours=(
                    int(entry["repair_maintenance_reference_hours"])
                    if entry.get("repair_maintenance_reference_hours") is not None
                    else None
                ),
                repair_maintenance_usage_multipliers=(
                    {
                        int(k): float(v)
                        for k, v in entry["repair_maintenance_usage_multipliers"].items()
                    }
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
    """
    Normalise a user-supplied role string into the keys used by ``machine_rates.json``.

    Parameters
    ----------
    role:
        Role label from the scenario or CLI (case-insensitive). ``None``/empty strings yield
        ``None`` so callers can guard optional inputs.

    Returns
    -------
    str | None
        Snake-cased role slug (e.g., ``roadside_processor``) or ``None`` if the input was blank.
    """

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
    """
    Return a cached mapping of ``normalised_role`` → ``MachineRate``.

    Normalisation folds similar roles together so helpers like processors or loaders can be looked
    up with CLI-friendly aliases (see ``ROLE_SYNONYMS``).
    """

    index: dict[str, MachineRate] = {}
    for rate in load_default_machine_rates():
        key = normalize_machine_role(rate.role) or rate.role
        index[key] = rate
    return index


def get_machine_rate(role: str) -> MachineRate | None:
    """
    Return the default machine rate entry for the supplied role.

    Parameters
    ----------
    role:
        Human-readable role (case-insensitive). Values are normalised via ``normalize_machine_role``.

    Returns
    -------
    MachineRate | None
        Matched reference entry, or ``None`` when the role is unknown.
    """

    normalised = normalize_machine_role(role)
    if normalised is None:
        return None
    return load_machine_rate_index().get(normalised)


def select_usage_class_multiplier(
    machine_rate: MachineRate, usage_hours: int | None
) -> tuple[int, float] | None:
    """
    Return the maintenance multiplier closest to the requested cumulative usage.

    Parameters
    ----------
    machine_rate:
        Reference machine entry including repair/maintenance lookup tables.
    usage_hours:
        Estimated machine age (SMH). ``None`` disables the lookup.

    Returns
    -------
    tuple[int, float] | None
        ``(bucket_hours, multiplier)`` pair taken from Advantage Vol. 4 No. 23, or ``None`` when
        the machine lacks the table or no usage was supplied.
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
        Source machine rate entry (owning + operating + optional repair/maintenance components).
    include_repair_maintenance:
        Whether to include the repair/maintenance allowance (True by default).
    ownership_override, operating_override, repair_override:
        Optional component overrides (pre-CPI). When ``None`` the values from ``machine_rate`` are
        used. ``repair_override`` beats ``usage_hours``.
    usage_hours:
        Approximate cumulative SMH used to select the repair multiplier bucket.

    Returns
    -------
    tuple[float, dict[str, float]]
        Rental rate per SMH and the raw component breakdown for auditability.
    """

    ownership = (
        ownership_override
        if ownership_override is not None
        else machine_rate.ownership_cost_per_smh
    )
    operating = (
        operating_override
        if operating_override is not None
        else machine_rate.operating_cost_per_smh
    )

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
