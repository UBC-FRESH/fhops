"""Net-profit evaluation for stand-scale serious-game levels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fhops.ground_system import simulate_ground_system
from fhops.scenario.contract import Scenario
from fhops.scenario.io import load_scenario
from fhops.stem import ReferenceStemModel, StemInventory, StemResult, build_stem_inventory
from fhops.tree_inventory import load_tree_inventory

from .careful_logging import DEFAULT_CAREFUL_LOGGING_CURVE, CarefulLoggingCurve
from .value import PriceSchedule

__all__ = ["OperationResult", "evaluate_kc_selection_cut"]


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Deterministic net-profit result for one stand-scale operation."""

    care_level: float
    processed_volume_m3: float
    gross_log_value: float
    machine_cost: float
    care_premium: float
    residual_asset_value: float
    residual_damage_loss: float
    mobilisation_cost: float
    road_extension_cost: float
    net_profit: float
    product_volume_m3: dict[str, float]
    product_value: dict[str, float]
    machine_hours: dict[str, float]
    makespan_s: float
    feller_productivity_multiplier: float
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable result."""
        return {
            "care_level": self.care_level,
            "processed_volume_m3": self.processed_volume_m3,
            "gross_log_value": self.gross_log_value,
            "machine_cost": self.machine_cost,
            "care_premium": self.care_premium,
            "residual_asset_value": self.residual_asset_value,
            "residual_damage_loss": self.residual_damage_loss,
            "mobilisation_cost": self.mobilisation_cost,
            "road_extension_cost": self.road_extension_cost,
            "net_profit": self.net_profit,
            "product_volume_m3": dict(sorted(self.product_volume_m3.items())),
            "product_value": dict(sorted(self.product_value.items())),
            "machine_hours": dict(sorted(self.machine_hours.items())),
            "makespan_s": self.makespan_s,
            "feller_productivity_multiplier": self.feller_productivity_multiplier,
            "warnings": list(self.warnings),
        }


def _default_machine_ids(scenario: Scenario) -> dict[str, Any]:
    by_role: dict[str, list[str]] = {}
    for machine in scenario.machines:
        if machine.role:
            by_role.setdefault(machine.role, []).append(machine.id)
    feller = by_role.get("feller_buncher") or by_role.get("harvester")
    if not feller:
        raise ValueError("Scenario has no feller-buncher/harvester.")
    loader = by_role.get("loader")
    if not loader:
        raise ValueError("Scenario has no loader.")
    skidders = by_role.get("grapple_skidder") or by_role.get("skidder")
    if not skidders:
        raise ValueError("Scenario has no grapple skidder.")
    return {
        "feller": feller[0],
        "skidders": tuple(skidders),
        "processors": tuple(by_role.get("roadside_processor", []) + by_role.get("processor", [])),
        "loader": loader[0],
    }


def _residual_trees(
    scenario_path: Path,
    scenario: Scenario,
    model: ReferenceStemModel,
) -> list[StemResult]:
    pin = scenario.tree_inventory
    if pin is None:
        raise ValueError("Scenario has no tree-inventory pin.")
    harvest_path = (scenario_path.parent / pin.inventory_path).resolve()
    residual_path = harvest_path.with_name("residual_trees.csv")
    residual_meta = harvest_path.with_name("residual.meta.json")
    if not residual_path.is_file() or not residual_meta.is_file():
        raise FileNotFoundError(
            f"Residual inventory missing next to {harvest_path.name}: "
            f"{residual_path.name}, {residual_meta.name}"
        )
    inventory = load_tree_inventory(
        residual_path,
        metadata_path=residual_meta,
        block_ids=set(scenario.block_ids()),
    )
    return [model.evaluate(row) for row in inventory.rows]


def evaluate_stand(
    scenario_path: str | Path,
    *,
    price_path: str | Path,
    care_level: float = 0.0,
    selection_cut: bool = False,
    form_factor: float = 0.45,
    log_length_m: float = 4.9,
    stump_height_m: float = 0.3,
    sawlog_min_dbh_cm: float = 20.0,
    road_extension_m: float = 0.0,
    shift_days: int = 30,
    hours_per_shift: float = 20.0,
    machine_ids: dict[str, Any] | None = None,
    care_curve: CarefulLoggingCurve = DEFAULT_CAREFUL_LOGGING_CURVE,
) -> OperationResult:
    """Evaluate one stand-scale operation and return net profit."""
    if form_factor <= 0 or log_length_m <= 0 or stump_height_m <= 0:
        raise ValueError("Stem and bucking parameters must be positive.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    scenario = load_scenario(scenario_file)
    price = PriceSchedule.from_path(price_path)
    model = ReferenceStemModel(
        form_factor=form_factor,
        log_length_m=log_length_m,
        stump_height_m=stump_height_m,
        sawlog_min_dbh_cm=sawlog_min_dbh_cm,
    )
    stems: StemInventory = build_stem_inventory(scenario_file, model=model)
    residual = _residual_trees(scenario_file, scenario, model) if selection_cut else []
    residual_asset = price.residual_asset_value(
        sum(tree.merchantable_volume_m3 for tree in residual)
    )
    if selection_cut:
        care = care_curve.get(care_level)
        feller_productivity = (
            care_curve.base_selection_cut_productivity_multiplier
            * care.care_productivity_multiplier
        )
        care_premium_per_m3 = care.care_premium_per_m3
        residual_damage_fraction = care.residual_damage_fraction
    else:
        care = None
        feller_productivity = 1.0
        care_premium_per_m3 = 0.0
        residual_damage_fraction = 0.0
    ids = machine_ids or _default_machine_ids(scenario)
    result = simulate_ground_system(
        scenario_file,
        block_id=scenario.blocks[0].id,
        feller_machine_id=str(ids["feller"]),
        skidder_machine_ids=tuple(ids["skidders"]),
        processor_machine_ids=tuple(ids["processors"]),
        loader_machine_id=str(ids["loader"]),
        stem_inventory=stems,
        shift_days=shift_days,
        hours_per_shift=hours_per_shift,
        feller_processing_time_multiplier=1.0 / feller_productivity,
    )
    stem_by_id = {tree.tree_id: tree for tree in stems.trees}
    processed_ids = {tree.tree_id for tree in result.trees}
    logs = [log for tree_id in processed_ids for log in stem_by_id[tree_id].logs]
    value = price.value_logs(logs)
    machine_costs = {machine.id: machine.operating_cost for machine in scenario.machines}
    machine_hours = {
        machine_id: float(summary["busy_s"]) / 3600.0
        for machine_id, summary in result.machine_summaries.items()
    }
    machine_cost = sum(
        hours * machine_costs.get(machine_id, 0.0) for machine_id, hours in machine_hours.items()
    )
    care_premium = result.processed_volume_m3 * care_premium_per_m3
    residual_damage_loss = residual_asset * residual_damage_fraction
    road_extension_cost = price.road_extension_cost(road_extension_m)
    net_profit = (
        float(value["gross_log_value"])
        - machine_cost
        - care_premium
        - residual_damage_loss
        - price.mobilisation_cost
        - road_extension_cost
    )
    return OperationResult(
        care_level=0.0 if care is None else care.level,
        processed_volume_m3=result.processed_volume_m3,
        gross_log_value=float(value["gross_log_value"]),
        machine_cost=machine_cost,
        care_premium=care_premium,
        residual_asset_value=residual_asset,
        residual_damage_loss=residual_damage_loss,
        mobilisation_cost=price.mobilisation_cost,
        road_extension_cost=road_extension_cost,
        net_profit=net_profit,
        product_volume_m3=dict(value["product_volume_m3"]),
        product_value=dict(value["product_value"]),
        machine_hours=machine_hours,
        makespan_s=result.makespan_s,
        feller_productivity_multiplier=feller_productivity,
        warnings=tuple(result.warnings),
    )


def evaluate_kc_selection_cut(
    scenario_path: str | Path,
    *,
    price_path: str | Path,
    care_level: float,
    form_factor: float = 0.192014,
    log_length_m: float = 4.9,
    stump_height_m: float = 0.3,
    sawlog_min_dbh_cm: float = 20.0,
    road_extension_m: float = 0.0,
    shift_days: int = 30,
    hours_per_shift: float = 20.0,
    machine_ids: dict[str, Any] | None = None,
    care_curve: CarefulLoggingCurve = DEFAULT_CAREFUL_LOGGING_CURVE,
) -> OperationResult:
    """Evaluate the KC selection-cut level."""
    return evaluate_stand(
        scenario_path,
        price_path=price_path,
        care_level=care_level,
        selection_cut=True,
        form_factor=form_factor,
        log_length_m=log_length_m,
        stump_height_m=stump_height_m,
        sawlog_min_dbh_cm=sawlog_min_dbh_cm,
        road_extension_m=road_extension_m,
        shift_days=shift_days,
        hours_per_shift=hours_per_shift,
        machine_ids=machine_ids,
        care_curve=care_curve,
    )
