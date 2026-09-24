"""YAML/CSV loaders for tactical–operational planning scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd
import yaml
from pydantic import TypeAdapter

from fhops.planning.tactical_operational.models import (
    Economics,
    ExternalSupply,
    Facility,
    FacilityDemand,
    FleetCapacity,
    HarvestSystemOption,
    InitialInventory,
    PlanningPeriod,
    PlanningUnit,
    Product,
    TacticalOperationalScenario,
    TransportArc,
)

_LIST_MODELS: dict[str, Any] = {
    "periods": list[PlanningPeriod],
    "products": list[Product],
    "planning_units": list[PlanningUnit],
    "harvest_system_options": list[HarvestSystemOption],
    "fleet_capacity": list[FleetCapacity],
    "facilities": list[Facility],
    "facility_demand": list[FacilityDemand],
    "initial_inventory": list[InitialInventory],
    "transport_arcs": list[TransportArc],
    "external_supply": list[ExternalSupply],
}


def _records_from_csv(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_csv(path)
    frame = frame.where(pd.notna(frame), None)
    return cast(list[dict[str, Any]], frame.to_dict("records"))


def _load_section(
    root: Path,
    payload: dict[str, Any],
    section: str,
) -> list[dict[str, Any]]:
    data_section = payload.get("data") or {}
    if section in data_section:
        path = Path(data_section[section])
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            raise FileNotFoundError(f"Tactical scenario section {section} not found: {path}")
        return _records_from_csv(path)
    rows = payload.get(section, [])
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise TypeError(f"Tactical scenario section {section} must be a list or CSV reference")
    return cast(list[dict[str, Any]], rows)


def load_tactical_operational_scenario(yaml_path: str | Path) -> TacticalOperationalScenario:
    """Load and validate a TOPM-inspired tactical–operational scenario.

    The loader accepts either inline YAML sections or a ``data:`` mapping from section names to CSV
    files. ``topm-mini``-style specifications may use ``fixture_id``/``specification_version``;
    those aliases are normalized to ``name`` and ``schema_version`` before Pydantic validation.
    """
    path = Path(yaml_path).resolve()
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise TypeError(f"Tactical scenario YAML must contain a mapping: {path}")
    payload = dict(payload)
    payload.setdefault("name", payload.get("fixture_id", path.stem))
    payload.setdefault("schema_version", payload.get("specification_version", "0.1.0"))
    payload.setdefault("planning_level", "tactical_operational")

    normalized: dict[str, Any] = {
        "name": payload["name"],
        "planning_level": payload["planning_level"],
        "schema_version": payload["schema_version"],
    }
    if "economics" in payload:
        normalized["economics"] = TypeAdapter(Economics).validate_python(payload["economics"])

    for section, model_type in _LIST_MODELS.items():
        rows = _load_section(path.parent, payload, section)
        normalized[section] = TypeAdapter(model_type).validate_python(rows)

    return TacticalOperationalScenario(**normalized)


def tactical_scenario_to_dict(scenario: TacticalOperationalScenario) -> dict[str, Any]:
    """Serialize a tactical–operational scenario to a JSON-compatible dictionary."""
    return scenario.model_dump(mode="json")


def tactical_scenario_dimensions(scenario: TacticalOperationalScenario) -> dict[str, int]:
    """Return model dimension counts for CLI output and telemetry."""
    return scenario.dimension_summary()


__all__ = [
    "load_tactical_operational_scenario",
    "tactical_scenario_dimensions",
    "tactical_scenario_to_dict",
]
