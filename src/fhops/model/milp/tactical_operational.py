"""TOPM-inspired tactical–operational MILP builder and driver.

This module implements the Phase 6 aggregate harvest-allocation core. It operates on
:class:`~fhops.planning.tactical_operational.TacticalOperationalScenario` objects and chooses
block × system × period harvest areas subject to semi-continuous minimum cut sizes, product yields,
fleet capacity, and facility demand targets. Product transport and facility inventory dynamics are
introduced by the follow-on flow module; this core model is deliberately small and auditable.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory

from fhops.planning.tactical_operational import TacticalOperationalScenario


class TacticalHarvestMode(StrEnum):
    """Supported harvest-quantity semantics for aggregate planning."""

    CONTINUOUS = "continuous"
    SEMI_CONTINUOUS = "semi_continuous"
    WHOLE_BLOCK = "whole_block"


class DemandBasis(StrEnum):
    """Facility demand envelope component enforced by the core MILP."""

    MINIMUM = "minimum"
    TARGET = "target"


@dataclass(frozen=True)
class TacticalOperationalMilpConfig:
    """Configuration for the aggregate tactical–operational MILP.

    Parameters
    ----------
    harvest_mode:
        Harvest-quantity semantics. ``semi_continuous`` enforces option-specific minimum active
        areas; ``continuous`` relaxes the minimum; ``whole_block`` forces the full operable area.
    demand_basis:
        Whether facility ``target_m3`` (default) or ``minimum_m3`` values drive required production.
    """

    harvest_mode: TacticalHarvestMode = TacticalHarvestMode.SEMI_CONTINUOUS
    demand_basis: DemandBasis = DemandBasis.TARGET


@dataclass(frozen=True)
class TacticalOperationalMilpBundle:
    """Normalized model bundle for tactical–operational MILP construction."""

    scenario: TacticalOperationalScenario
    config: TacticalOperationalMilpConfig


def build_tactical_operational_bundle(
    scenario: TacticalOperationalScenario,
    *,
    harvest_mode: TacticalHarvestMode | str = TacticalHarvestMode.SEMI_CONTINUOUS,
    demand_basis: DemandBasis | str = DemandBasis.TARGET,
) -> TacticalOperationalMilpBundle:
    """Create a tactical MILP bundle from a validated scenario."""
    return TacticalOperationalMilpBundle(
        scenario=scenario,
        config=TacticalOperationalMilpConfig(
            harvest_mode=TacticalHarvestMode(harvest_mode),
            demand_basis=DemandBasis(demand_basis),
        ),
    )


def tactical_bundle_to_dict(bundle: TacticalOperationalMilpBundle) -> dict[str, Any]:
    """Serialize a tactical MILP bundle for reproducible replay."""
    return {
        "scenario": bundle.scenario.to_dict(),
        "config": {
            "harvest_mode": bundle.config.harvest_mode.value,
            "demand_basis": bundle.config.demand_basis.value,
        },
    }


def tactical_bundle_from_dict(payload: Mapping[str, Any]) -> TacticalOperationalMilpBundle:
    """Rebuild a tactical MILP bundle from :func:`tactical_bundle_to_dict` output."""
    scenario = TacticalOperationalScenario.model_validate(payload["scenario"])
    config_payload = payload.get("config", {})
    return build_tactical_operational_bundle(
        scenario,
        harvest_mode=config_payload.get("harvest_mode", TacticalHarvestMode.SEMI_CONTINUOUS.value),
        demand_basis=config_payload.get("demand_basis", DemandBasis.TARGET.value),
    )


def build_tactical_operational_model(bundle: TacticalOperationalMilpBundle) -> pyo.ConcreteModel:
    """Build the aggregate harvest/system/period MILP.

    Variables are generated only for eligible harvest-system options. Activation binaries use the
    option's physical area/productivity bounds rather than arbitrary big-M constants.
    """
    scenario = bundle.scenario
    config = bundle.config
    options = [option for option in scenario.harvest_system_options if option.eligible]
    if not options:
        raise ValueError("Tactical MILP requires at least one eligible harvest system option")

    blocks = {unit.block_id: unit for unit in scenario.planning_units}
    periods = {period.period_id: period for period in scenario.periods}
    products = [product.product_id for product in scenario.products]

    model = pyo.ConcreteModel(name=f"tactical_operational:{scenario.name}")
    model.O = pyo.Set(initialize=[option.option_id for option in options])
    model.B = pyo.Set(initialize=[unit.block_id for unit in scenario.planning_units])
    model.T = pyo.Set(initialize=[period.period_id for period in scenario.periods])
    model.P = pyo.Set(initialize=products)

    model.area = pyo.Var(model.O, domain=pyo.NonNegativeReals)
    model.harvest_active = pyo.Var(model.O, domain=pyo.Binary)
    model.product_volume = pyo.Var(model.O, model.P, domain=pyo.NonNegativeReals)

    def _max_area(option_id: str) -> float:
        option = option_by_id[option_id]
        block = blocks[option.block_id]
        return option.max_area_ha if option.max_area_ha is not None else block.operable_area_ha

    option_by_id = {option.option_id: option for option in options}

    def harvest_upper_rule(mdl: pyo.ConcreteModel, option_id: str):
        return mdl.area[option_id] <= _max_area(option_id) * mdl.harvest_active[option_id]

    model.harvest_upper = pyo.Constraint(model.O, rule=harvest_upper_rule)

    if config.harvest_mode == TacticalHarvestMode.SEMI_CONTINUOUS:

        def harvest_lower_rule(mdl: pyo.ConcreteModel, option_id: str):
            option = option_by_id[option_id]
            return mdl.area[option_id] >= option.min_area_ha * mdl.harvest_active[option_id]

        model.harvest_lower = pyo.Constraint(model.O, rule=harvest_lower_rule)
    elif config.harvest_mode == TacticalHarvestMode.WHOLE_BLOCK:

        def whole_block_rule(mdl: pyo.ConcreteModel, option_id: str):
            option = option_by_id[option_id]
            block = blocks[option.block_id]
            return mdl.area[option_id] == block.operable_area_ha * mdl.harvest_active[option_id]

        model.whole_block = pyo.Constraint(model.O, rule=whole_block_rule)

    def productivity_cap_rule(mdl: pyo.ConcreteModel, option_id: str):
        option = option_by_id[option_id]
        if option.productivity_m3_per_period is None:
            return pyo.Constraint.Skip
        block = blocks[option.block_id]
        yield_per_ha = sum(block.product_yields_m3_per_ha.values())
        return (
            yield_per_ha * mdl.area[option_id]
            <= option.productivity_m3_per_period * mdl.harvest_active[option_id]
        )

    model.productivity_cap = pyo.Constraint(model.O, rule=productivity_cap_rule)

    def product_conversion_rule(mdl: pyo.ConcreteModel, option_id: str, product_id: str):
        option = option_by_id[option_id]
        block = blocks[option.block_id]
        yield_per_ha = block.product_yields_m3_per_ha.get(product_id, 0.0)
        return mdl.product_volume[option_id, product_id] == yield_per_ha * mdl.area[option_id]

    model.product_conversion = pyo.Constraint(model.O, model.P, rule=product_conversion_rule)

    def block_area_rule(mdl: pyo.ConcreteModel, block_id: str):
        block_options = [option for option in options if option.block_id == block_id]
        if not block_options:
            return pyo.Constraint.Skip
        return (
            sum(mdl.area[option.option_id] for option in block_options)
            <= blocks[block_id].operable_area_ha
        )

    model.block_area = pyo.Constraint(model.B, rule=block_area_rule)

    capacity_by_system_period: dict[tuple[str, str], list[str]] = defaultdict(list)
    for option in options:
        capacity_by_system_period[(option.system_id, option.period_id)].append(option.option_id)

    def fleet_capacity_rule(mdl: pyo.ConcreteModel, system_id: str, period_id: str):
        capacity_rows = [
            row
            for row in scenario.fleet_capacity
            if row.system_id == system_id and row.period_id == period_id
        ]
        if not capacity_rows:
            return pyo.Constraint.Skip
        capacity_m3 = [row.capacity_m3 for row in capacity_rows if row.capacity_m3 is not None]
        if not capacity_m3:
            return pyo.Constraint.Skip
        option_ids = capacity_by_system_period.get((system_id, period_id), [])
        if not option_ids:
            return pyo.Constraint.Skip
        expr = 0
        for option_id in option_ids:
            option = option_by_id[option_id]
            block = blocks[option.block_id]
            expr += sum(block.product_yields_m3_per_ha.values()) * mdl.area[option_id]
        return expr <= min(capacity_m3)

    fleet_keys = sorted(capacity_by_system_period)
    model.FleetKeys = pyo.Set(initialize=fleet_keys, dimen=2)
    model.fleet_capacity = pyo.Constraint(model.FleetKeys, rule=fleet_capacity_rule)

    demand_requirements: dict[tuple[str, str], float] = defaultdict(float)
    for demand in scenario.facility_demand:
        value = demand.target_m3 if config.demand_basis == DemandBasis.TARGET else demand.minimum_m3
        if value is None:
            continue
        demand_requirements[(demand.product_id, demand.period_id)] += value

    options_by_product_period: dict[tuple[str, str], list[str]] = defaultdict(list)
    for option in options:
        block = blocks[option.block_id]
        for product_id, yield_per_ha in block.product_yields_m3_per_ha.items():
            if yield_per_ha > 0:
                options_by_product_period[(product_id, option.period_id)].append(option.option_id)

    model.DemandKeys = pyo.Set(initialize=sorted(demand_requirements), dimen=2)

    def demand_rule(mdl: pyo.ConcreteModel, product_id: str, period_id: str):
        option_ids = options_by_product_period.get((product_id, period_id), [])
        if not option_ids:
            return pyo.Constraint.Skip
        return (
            sum(mdl.product_volume[option_id, product_id] for option_id in option_ids)
            >= demand_requirements[(product_id, period_id)]
        )

    model.demand = pyo.Constraint(model.DemandKeys, rule=demand_rule)

    objective = 0
    for option in options:
        period = periods[option.period_id]
        block = blocks[option.block_id]
        total_yield = sum(block.product_yields_m3_per_ha.values())
        fixed = period.discount_factor * option.fixed_cost * model.harvest_active[option.option_id]
        variable = (
            period.discount_factor
            * option.variable_cost_per_m3
            * total_yield
            * model.area[option.option_id]
        )
        objective += fixed + variable

    model.objective = pyo.Objective(expr=objective, sense=pyo.minimize)
    model._tactical_meta = {
        "bundle": bundle,
        "options": tuple(option.option_id for option in options),
        "blocks": blocks,
        "periods": periods,
        "products": tuple(products),
        "demand_requirements": dict(demand_requirements),
    }
    return model


def solve_tactical_operational_milp(
    bundle: TacticalOperationalMilpBundle,
    *,
    solver: str = "highs",
    time_limit: int | None = None,
    gap: float | None = None,
    tee: bool = False,
    solver_options: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Build and solve the tactical–operational harvest-allocation MILP.

    Returns a dictionary containing solver status, objective decomposition, harvest decisions,
    product production, and model dimensions. The objective is discounted delivered harvest cost;
    transport, purchases, and facility inventory costs are handled by the follow-on flow module.
    """
    started = time.perf_counter()
    model = build_tactical_operational_model(bundle)
    opt = SolverFactory(solver)
    if time_limit is not None:
        opt.options["time_limit"] = time_limit
    if gap is not None:
        opt.options["mipgap"] = gap
        if solver.lower() not in {"gurobi", "cplex"}:
            opt.options["mip_rel_gap"] = gap
    if solver_options:
        for key, value in solver_options.items():
            opt.options[str(key)] = value
    result = opt.solve(model, tee=tee, load_solutions=True)
    runtime_s = time.perf_counter() - started

    status = str(result.solver.status).lower()
    termination = str(result.solver.termination_condition).lower()
    solved = termination in {"optimal", "feasible"} or status in {"optimal", "feasible"}

    if solved:
        harvest = _extract_harvest_decisions(model)
        production = _extract_production(model)
        objective_components = _objective_components(harvest)
        objective = pyo.value(model.objective)
    else:
        harvest = pd.DataFrame(
            columns=[
                "option_id",
                "block_id",
                "system_id",
                "period_id",
                "active",
                "harvested_area_ha",
                "total_volume_m3",
                "fixed_cost",
                "variable_cost",
                "discounted_cost",
            ]
        )
        production = pd.DataFrame(
            columns=["option_id", "block_id", "system_id", "period_id", "product_id", "volume_m3"]
        )
        objective_components = {}
        objective = None

    return {
        "objective": objective,
        "objective_components": objective_components,
        "harvest_decisions": harvest,
        "production": production,
        "model_dimensions": bundle.scenario.dimension_summary(),
        "solver_status": str(result.solver.status),
        "termination_condition": str(result.solver.termination_condition),
        "runtime_s": runtime_s,
        "config": {
            "harvest_mode": bundle.config.harvest_mode.value,
            "demand_basis": bundle.config.demand_basis.value,
        },
    }


def _extract_harvest_decisions(model: pyo.ConcreteModel) -> pd.DataFrame:
    meta = model._tactical_meta
    bundle: TacticalOperationalMilpBundle = meta["bundle"]
    blocks = meta["blocks"]
    periods = meta["periods"]
    rows: list[dict[str, Any]] = []
    for option_id in meta["options"]:
        option = next(
            option
            for option in bundle.scenario.harvest_system_options
            if option.option_id == option_id
        )
        area = float(pyo.value(model.area[option_id]))
        active = int(pyo.value(model.harvest_active[option_id]) > 0.5)
        if area <= 1e-9 and not active:
            continue
        block = blocks[option.block_id]
        period = periods[option.period_id]
        total_volume = area * sum(block.product_yields_m3_per_ha.values())
        fixed = period.discount_factor * option.fixed_cost * active
        variable = period.discount_factor * option.variable_cost_per_m3 * total_volume
        rows.append(
            {
                "option_id": option.option_id,
                "block_id": option.block_id,
                "system_id": option.system_id,
                "period_id": option.period_id,
                "active": active,
                "harvested_area_ha": area,
                "total_volume_m3": total_volume,
                "fixed_cost": fixed,
                "variable_cost": variable,
                "discounted_cost": fixed + variable,
            }
        )
    return pd.DataFrame(rows)


def _extract_production(model: pyo.ConcreteModel) -> pd.DataFrame:
    meta = model._tactical_meta
    bundle: TacticalOperationalMilpBundle = meta["bundle"]
    rows: list[dict[str, Any]] = []
    for option_id in meta["options"]:
        option = next(
            option
            for option in bundle.scenario.harvest_system_options
            if option.option_id == option_id
        )
        for product_id in meta["products"]:
            volume = float(pyo.value(model.product_volume[option_id, product_id]))
            if volume <= 1e-9:
                continue
            rows.append(
                {
                    "option_id": option_id,
                    "block_id": option.block_id,
                    "system_id": option.system_id,
                    "period_id": option.period_id,
                    "product_id": product_id,
                    "volume_m3": volume,
                }
            )
    return pd.DataFrame(rows)


def _objective_components(harvest: pd.DataFrame) -> dict[str, float]:
    if harvest.empty:
        return {"fixed_cost": 0.0, "variable_cost": 0.0, "total_cost": 0.0}
    fixed = float(harvest["fixed_cost"].sum())
    variable = float(harvest["variable_cost"].sum())
    return {"fixed_cost": fixed, "variable_cost": variable, "total_cost": fixed + variable}


__all__ = [
    "DemandBasis",
    "TacticalHarvestMode",
    "TacticalOperationalMilpBundle",
    "TacticalOperationalMilpConfig",
    "build_tactical_operational_bundle",
    "build_tactical_operational_model",
    "solve_tactical_operational_milp",
    "tactical_bundle_from_dict",
    "tactical_bundle_to_dict",
]
