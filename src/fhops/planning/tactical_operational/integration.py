"""Tactical→operational handoff and rolling-state helpers for Phase 6."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

import pandas as pd
import yaml

from fhops.planning.tactical_operational.models import TacticalOperationalScenario
from fhops.scenario.contract.models import Scenario


@dataclass(frozen=True)
class TacticalCommitment:
    """A selected aggregate block/system/period commitment."""

    block_id: str
    system_id: str
    period_id: str
    area_ha: float
    total_volume_m3: float
    product_volumes_m3: dict[str, float] = field(default_factory=dict)


@dataclass
class TacticalRollingState:
    """Aggregate state carried between tactical–operational planning iterations."""

    remaining_area_ha: dict[str, float]
    remaining_product_volume_m3: dict[tuple[str, str], float]
    facility_inventory_m3: dict[tuple[str, str], float]
    active_roads: set[str]
    fleet_units: dict[str, int]
    cumulative_costs: dict[str, float]
    commitments: list[TacticalCommitment]


def commitments_from_result(result: dict[str, Any]) -> list[TacticalCommitment]:
    """Extract selected harvest commitments from a tactical solve result payload."""
    harvest = _records(result.get("harvest_decisions"))
    production = _records(result.get("production"))
    production_by_option: dict[str, dict[str, float]] = {}
    for row in production:
        option_id = str(row.get("option_id"))
        production_by_option.setdefault(option_id, {})[str(row.get("product_id"))] = float(
            row.get("volume_m3") or 0.0
        )
    commitments: list[TacticalCommitment] = []
    for row in harvest:
        option_id = str(row.get("option_id"))
        area = float(row.get("harvested_area_ha") or 0.0)
        if area <= 0:
            continue
        commitments.append(
            TacticalCommitment(
                block_id=str(row.get("block_id")),
                system_id=str(row.get("system_id")),
                period_id=str(row.get("period_id")),
                area_ha=area,
                total_volume_m3=float(row.get("total_volume_m3") or 0.0),
                product_volumes_m3=production_by_option.get(option_id, {}),
            )
        )
    return commitments


def build_tactical_rolling_state(
    scenario: TacticalOperationalScenario,
    result: dict[str, Any],
) -> TacticalRollingState:
    """Build a rolling state snapshot from a tactical scenario and solve result."""
    commitments = commitments_from_result(result)
    harvested_area: dict[str, float] = {}
    harvested_products: dict[tuple[str, str], float] = {}
    for commitment in commitments:
        harvested_area[commitment.block_id] = (
            harvested_area.get(commitment.block_id, 0.0) + commitment.area_ha
        )
        for product_id, volume in commitment.product_volumes_m3.items():
            key = (commitment.block_id, product_id)
            harvested_products[key] = harvested_products.get(key, 0.0) + volume

    remaining_area: dict[str, float] = {}
    remaining_products: dict[tuple[str, str], float] = {}
    for block in scenario.planning_units:
        remaining_area[block.block_id] = max(
            0.0,
            block.operable_area_ha - harvested_area.get(block.block_id, 0.0),
        )
        for product_id, yield_per_ha in block.product_yields_m3_per_ha.items():
            key = (block.block_id, product_id)
            initial = block.operable_area_ha * yield_per_ha
            remaining_products[key] = max(
                0.0,
                initial - harvested_products.get(key, 0.0),
            )

    inventory_records = _records(result.get("inventory"))
    final_inventory: dict[tuple[str, str], float] = {}
    if inventory_records:
        final_period = max(str(row.get("period_id")) for row in inventory_records)
        for row in inventory_records:
            if str(row.get("period_id")) == final_period:
                final_inventory[(str(row.get("facility_id")), str(row.get("product_id")))] = float(
                    row.get("closing_m3") or 0.0
                )

    active_roads = {
        str(row.get("road_id"))
        for row in _records(result.get("roads"))
        if int(row.get("available") or 0) == 1
    }
    fleet_units = {
        str(row.get("option_id")): int(row.get("units") or 0)
        for row in _records(result.get("fleet"))
    }
    return TacticalRollingState(
        remaining_area_ha=remaining_area,
        remaining_product_volume_m3=remaining_products,
        facility_inventory_m3=final_inventory,
        active_roads=active_roads,
        fleet_units=fleet_units,
        cumulative_costs=dict(result.get("objective_components") or {}),
        commitments=commitments,
    )


def compile_business_window_scenario(
    base: Scenario,
    commitments: list[TacticalCommitment],
    *,
    block_map: dict[str, str] | None = None,
    start_day: int = 1,
    horizon_days: int | None = None,
) -> Scenario:
    """Compile tactical commitments into a filtered operational scenario.

    The base operational scenario provides machines, calendars, production rates, landings, and
    mobilisation tables. Tactical commitments select eligible blocks and override their harvest
    system IDs. Block windows are clamped to the requested business window without rebasing days.
    """
    mapping = block_map or {}
    selected: dict[str, TacticalCommitment] = {}
    for commitment in commitments:
        operational_id = mapping.get(commitment.block_id, commitment.block_id)
        selected[operational_id] = commitment
    if not selected:
        raise ValueError("No tactical commitments available for operational compilation")

    horizon_end = start_day + horizon_days - 1 if horizon_days else base.num_days
    scenario = base.model_copy(deep=True)
    blocks = []
    for block in scenario.blocks:
        if block.id not in selected:
            continue
        commitment = selected[block.id]
        updated = block.model_copy(deep=True)
        updated.harvest_system_id = commitment.system_id
        earliest = updated.earliest_start or 1
        latest = updated.latest_finish or scenario.num_days
        updated.earliest_start = max(earliest, start_day)
        updated.latest_finish = min(latest, horizon_end)
        if updated.latest_finish < updated.earliest_start:
            raise ValueError(
                f"Tactical commitment for block {block.id} lies outside the business window"
            )
        blocks.append(updated)
    if not blocks:
        raise ValueError("No operational blocks matched the tactical commitments")
    scenario.blocks = blocks
    kept = {block.id for block in blocks}
    scenario.production_rates = [
        rate for rate in scenario.production_rates if rate.block_id in kept
    ]
    if scenario.mobilisation and scenario.mobilisation.distances:
        scenario.mobilisation = scenario.mobilisation.model_copy(
            update={
                "distances": [
                    distance
                    for distance in scenario.mobilisation.distances
                    if distance.from_block in kept and distance.to_block in kept
                ]
            }
        )
    return scenario


def apply_operational_realization(
    state: TacticalRollingState,
    assignments: pd.DataFrame,
    *,
    yield_per_ha: dict[str, float],
    block_map: dict[str, str] | None = None,
) -> TacticalRollingState:
    """Update block/product state from realized operational assignment production.

    ``yield_per_ha`` maps operational block IDs to total m³/ha. Production is treated as aggregate
    delivered volume unless callers pre-aggregate product-specific flows and update
    ``facility_inventory_m3`` separately.
    """
    mapping = block_map or {}
    realized: dict[str, float] = {}
    realized_ids: dict[str, str] = {}
    for row in assignments.itertuples(index=False):
        block_id = str(getattr(row, "block_id"))
        production = float(getattr(row, "production", 0.0) or 0.0)
        tactical_block = mapping.get(block_id, block_id)
        realized[tactical_block] = realized.get(tactical_block, 0.0) + production
        realized_ids[tactical_block] = block_id

    for block_id, volume in realized.items():
        total_yield = yield_per_ha.get(
            realized_ids.get(block_id, block_id),
            yield_per_ha.get(block_id, 0.0),
        )
        if total_yield <= 0:
            continue
        area_done = min(state.remaining_area_ha.get(block_id, 0.0), volume / total_yield)
        state.remaining_area_ha[block_id] = max(
            0.0, state.remaining_area_ha.get(block_id, 0.0) - area_done
        )
        product_keys = [key for key in state.remaining_product_volume_m3 if key[0] == block_id]
        current_total = sum(state.remaining_product_volume_m3[key] for key in product_keys)
        for key in product_keys:
            if current_total <= 0:
                continue
            share = state.remaining_product_volume_m3[key] / current_total
            state.remaining_product_volume_m3[key] = max(
                0.0,
                state.remaining_product_volume_m3[key] - volume * share,
            )
    return state


def write_operational_scenario_bundle(scenario: Scenario, out_dir: str | Path) -> Path:
    """Write an operational scenario object as a YAML/CSV bundle compatible with ``load_scenario``."""
    root = Path(out_dir)
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_records(
        [block.model_dump(mode="json") for block in scenario.blocks], data_dir / "blocks.csv"
    )
    _write_records(
        [machine.model_dump(mode="json") for machine in scenario.machines],
        data_dir / "machines.csv",
    )
    _write_records(
        [landing.model_dump(mode="json") for landing in scenario.landings],
        data_dir / "landings.csv",
    )
    _write_records(
        [entry.model_dump(mode="json") for entry in scenario.calendar],
        data_dir / "calendar.csv",
    )
    _write_records(
        [rate.model_dump(mode="json") for rate in scenario.production_rates],
        data_dir / "prod_rates.csv",
    )
    if scenario.shift_calendar:
        _write_records(
            [entry.model_dump(mode="json") for entry in scenario.shift_calendar],
            data_dir / "shift_calendar.csv",
        )
    metadata: dict[str, Any] = {
        "name": scenario.name,
        "num_days": scenario.num_days,
        "schema_version": scenario.schema_version,
        "data": {
            "blocks": "data/blocks.csv",
            "machines": "data/machines.csv",
            "landings": "data/landings.csv",
            "calendar": "data/calendar.csv",
            "prod_rates": "data/prod_rates.csv",
        },
    }
    if scenario.start_date:
        metadata["start_date"] = scenario.start_date.isoformat()
    if scenario.shift_calendar:
        metadata["data"]["shift_calendar"] = "data/shift_calendar.csv"
    if scenario.harvest_systems:
        metadata["harvest_systems"] = {
            key: json.loads(json.dumps(asdict(value), default=list))
            for key, value in scenario.harvest_systems.items()
        }
    yaml_path = root / "scenario.yaml"
    yaml_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    return yaml_path


def _write_records(records: list[dict[str, Any]], path: Path) -> None:
    frame = pd.DataFrame(records)
    frame = frame.dropna(axis=1, how="all")
    frame.to_csv(path, index=False)


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame):
        return [cast(dict[str, Any], row) for row in value.to_dict("records")]
    if isinstance(value, list):
        return [dict(row) for row in value]
    return []


__all__ = [
    "TacticalCommitment",
    "TacticalRollingState",
    "apply_operational_realization",
    "build_tactical_rolling_state",
    "commitments_from_result",
    "compile_business_window_scenario",
    "write_operational_scenario_bundle",
]
