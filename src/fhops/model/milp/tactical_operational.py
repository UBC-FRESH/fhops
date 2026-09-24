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
from typing import Any, cast

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
    """Facility demand envelope component enforced by the tactical–operational MILP."""

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
    period_order = sorted(scenario.periods, key=lambda period: period.sequence)
    products = [product.product_id for product in scenario.products]
    arcs = list(scenario.transport_arcs)
    supplies = list(scenario.external_supply)
    facilities = {facility.facility_id: facility for facility in scenario.facilities}
    opening_inventory = {
        (row.facility_id, row.product_id): row.opening_m3 for row in scenario.initial_inventory
    }
    demand_by_key = {
        (row.facility_id, row.product_id, row.period_id): row for row in scenario.facility_demand
    }
    facility_product_periods = sorted(
        {
            (facility.facility_id, product_id, period.period_id)
            for facility in scenario.facilities
            for product_id in (facility.accepted_products or products)
            for period in scenario.periods
        }
    )

    model = pyo.ConcreteModel(name=f"tactical_operational:{scenario.name}")
    model.O = pyo.Set(initialize=[option.option_id for option in options])
    model.B = pyo.Set(initialize=[unit.block_id for unit in scenario.planning_units])
    model.T = pyo.Set(initialize=[period.period_id for period in scenario.periods])
    model.P = pyo.Set(initialize=products)
    model.A = pyo.Set(initialize=[arc.arc_id for arc in arcs])
    supply_keys = [
        (supply.source_id, supply.destination_id, supply.product_id, supply.period_id)
        for supply in supplies
    ]
    model.Supply = pyo.Set(initialize=supply_keys, dimen=4)
    model.FacilityKeys = pyo.Set(initialize=facility_product_periods, dimen=3)

    model.area = pyo.Var(model.O, domain=pyo.NonNegativeReals)
    model.harvest_active = pyo.Var(model.O, domain=pyo.Binary)
    model.product_volume = pyo.Var(model.O, model.P, domain=pyo.NonNegativeReals)
    model.flow = pyo.Var(model.A, domain=pyo.NonNegativeReals)
    model.purchase = pyo.Var(model.Supply, domain=pyo.NonNegativeReals)
    model.consumption = pyo.Var(model.FacilityKeys, domain=pyo.NonNegativeReals)
    model.inventory = pyo.Var(model.FacilityKeys, domain=pyo.NonNegativeReals)

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

    arcs_by_origin_product_period: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    arcs_by_destination_product_period: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    arc_by_id = {arc.arc_id: arc for arc in arcs}
    for arc in arcs:
        arcs_by_origin_product_period[(arc.origin_id, arc.product_id, arc.period_id)].append(
            arc.arc_id
        )
        arcs_by_destination_product_period[
            (arc.destination_id, arc.product_id, arc.period_id)
        ].append(arc.arc_id)

    supply_keys_by_destination_product_period: dict[
        tuple[str, str, str], list[tuple[str, str, str, str]]
    ] = defaultdict(list)
    supply_by_key = {
        (supply.source_id, supply.destination_id, supply.product_id, supply.period_id): supply
        for supply in supplies
    }
    for supply_key in supply_keys:
        supply = supply_by_key[supply_key]
        supply_keys_by_destination_product_period[
            (supply.destination_id, supply.product_id, supply.period_id)
        ].append(supply_key)

    production_keys = sorted(
        {
            (block_id, product_id, period.period_id)
            for block_id in blocks
            for product_id in products
            for period in scenario.periods
        }
    )
    model.ProductionKeys = pyo.Set(initialize=production_keys, dimen=3)

    def flow_supply_rule(mdl: pyo.ConcreteModel, block_id: str, product_id: str, period_id: str):
        option_ids = [
            option.option_id
            for option in options
            if option.block_id == block_id and option.period_id == period_id
        ]
        outgoing = arcs_by_origin_product_period.get((block_id, product_id, period_id), [])
        if not outgoing:
            return pyo.Constraint.Skip
        if not option_ids:
            return sum(mdl.flow[arc_id] for arc_id in outgoing) == 0
        return sum(mdl.flow[arc_id] for arc_id in outgoing) <= sum(
            mdl.product_volume[option_id, product_id] for option_id in option_ids
        )

    model.flow_supply = pyo.Constraint(model.ProductionKeys, rule=flow_supply_rule)

    def arc_capacity_rule(mdl: pyo.ConcreteModel, arc_id: str):
        arc = arc_by_id[arc_id]
        if arc.capacity_m3 is None:
            return pyo.Constraint.Skip
        return mdl.flow[arc_id] <= arc.capacity_m3

    model.arc_capacity = pyo.Constraint(model.A, rule=arc_capacity_rule)

    def purchase_lower_rule(
        mdl: pyo.ConcreteModel,
        source_id: str,
        destination_id: str,
        product_id: str,
        period_id: str,
    ):
        supply = supply_by_key[(source_id, destination_id, product_id, period_id)]
        return mdl.purchase[(source_id, destination_id, product_id, period_id)] >= supply.minimum_m3

    def purchase_upper_rule(
        mdl: pyo.ConcreteModel,
        source_id: str,
        destination_id: str,
        product_id: str,
        period_id: str,
    ):
        supply = supply_by_key[(source_id, destination_id, product_id, period_id)]
        if supply.maximum_m3 is None:
            return pyo.Constraint.Skip
        return mdl.purchase[(source_id, destination_id, product_id, period_id)] <= supply.maximum_m3

    model.purchase_lower = pyo.Constraint(model.Supply, rule=purchase_lower_rule)
    model.purchase_upper = pyo.Constraint(model.Supply, rule=purchase_upper_rule)

    def consumption_lower_rule(
        mdl: pyo.ConcreteModel, facility_id: str, product_id: str, period_id: str
    ):
        demand = demand_by_key.get((facility_id, product_id, period_id))
        var = mdl.consumption[(facility_id, product_id, period_id)]
        if demand is None:
            return var == 0
        return var >= demand.minimum_m3

    def consumption_target_rule(
        mdl: pyo.ConcreteModel, facility_id: str, product_id: str, period_id: str
    ):
        demand = demand_by_key.get((facility_id, product_id, period_id))
        if demand is None or config.demand_basis != DemandBasis.TARGET or demand.target_m3 is None:
            return pyo.Constraint.Skip
        return mdl.consumption[(facility_id, product_id, period_id)] == demand.target_m3

    def consumption_upper_rule(
        mdl: pyo.ConcreteModel, facility_id: str, product_id: str, period_id: str
    ):
        demand = demand_by_key.get((facility_id, product_id, period_id))
        if demand is None or demand.maximum_m3 is None:
            return pyo.Constraint.Skip
        return mdl.consumption[(facility_id, product_id, period_id)] <= demand.maximum_m3

    model.consumption_lower = pyo.Constraint(model.FacilityKeys, rule=consumption_lower_rule)
    model.consumption_target = pyo.Constraint(model.FacilityKeys, rule=consumption_target_rule)
    model.consumption_upper = pyo.Constraint(model.FacilityKeys, rule=consumption_upper_rule)

    previous_period: dict[str, str | None] = {}
    for index, period in enumerate(period_order):
        previous_period[period.period_id] = period_order[index - 1].period_id if index > 0 else None

    def inventory_balance_rule(
        mdl: pyo.ConcreteModel, facility_id: str, product_id: str, period_id: str
    ):
        previous_id = previous_period[period_id]
        if previous_id is None:
            opening = opening_inventory.get((facility_id, product_id), 0.0)
        else:
            opening = mdl.inventory[(facility_id, product_id, previous_id)]
        incoming = sum(
            mdl.flow[arc_id]
            for arc_id in arcs_by_destination_product_period.get(
                (facility_id, product_id, period_id), []
            )
        )
        purchases = sum(
            mdl.purchase[supply_key]
            for supply_key in supply_keys_by_destination_product_period.get(
                (facility_id, product_id, period_id), []
            )
        )
        return (
            mdl.inventory[(facility_id, product_id, period_id)]
            == opening
            + incoming
            + purchases
            - mdl.consumption[(facility_id, product_id, period_id)]
        )

    model.inventory_balance = pyo.Constraint(model.FacilityKeys, rule=inventory_balance_rule)

    cost_expr = 0
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
        cost_expr += fixed + variable
    for arc in arcs:
        period = periods[arc.period_id]
        cost_expr += period.discount_factor * arc.cost_per_m3 * model.flow[arc.arc_id]
    for supply_key in supply_keys:
        supply = supply_by_key[supply_key]
        period = periods[supply.period_id]
        cost_expr += (
            period.discount_factor * supply.delivered_cost_per_m3 * model.purchase[supply_key]
        )

    objective_profile = scenario.economics.objective_profile
    if objective_profile == "min_discounted_delivered_cost":
        objective_expr = cost_expr
        objective_sense = pyo.minimize
    else:
        value_expr = 0
        for demand in scenario.facility_demand:
            if demand.value_per_m3 is None:
                continue
            period = periods[demand.period_id]
            key = (demand.facility_id, demand.product_id, demand.period_id)
            value_expr += period.discount_factor * demand.value_per_m3 * model.consumption[key]
        terminal_value_expr = 0
        if objective_profile == "max_npv":
            final_period = period_order[-1].period_id
            for facility_id, facility in facilities.items():
                terminal_values = facility.terminal_inventory_value_per_m3 or {}
                for product_id, value_per_m3 in terminal_values.items():
                    terminal_value_expr += (
                        periods[final_period].discount_factor
                        * value_per_m3
                        * model.inventory[(facility_id, product_id, final_period)]
                    )
        if objective_profile not in {"max_discounted_profit", "max_npv"}:
            raise ValueError(
                "Unsupported tactical objective_profile="
                f"{objective_profile}; use min_discounted_delivered_cost, "
                "max_discounted_profit, or max_npv"
            )
        objective_expr = value_expr + terminal_value_expr - cost_expr
        objective_sense = pyo.maximize

    model.objective = pyo.Objective(expr=objective_expr, sense=objective_sense)
    model._tactical_meta = {
        "bundle": bundle,
        "options": tuple(option.option_id for option in options),
        "blocks": blocks,
        "periods": periods,
        "products": tuple(products),
        "arcs": tuple(arc.arc_id for arc in arcs),
        "arc_by_id": arc_by_id,
        "supplies": tuple(supply_keys),
        "supply_by_key": supply_by_key,
        "facility_keys": tuple(facility_product_periods),
        "demand_by_key": demand_by_key,
        "opening_inventory": opening_inventory,
        "previous_period": previous_period,
        "facilities": facilities,
        "final_period_id": period_order[-1].period_id,
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
        flows = _extract_flows(model)
        purchases = _extract_purchases(model)
        inventory = _extract_inventory(model)
        consumption = _extract_consumption(model)
        objective_components = _objective_components(
            model, harvest, flows, purchases, consumption, inventory
        )
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
        flows = pd.DataFrame(
            columns=[
                "arc_id",
                "origin_id",
                "destination_id",
                "product_id",
                "period_id",
                "mode",
                "volume_m3",
                "transport_cost",
            ]
        )
        purchases = pd.DataFrame(
            columns=[
                "source_id",
                "destination_id",
                "product_id",
                "period_id",
                "volume_m3",
                "purchase_cost",
            ]
        )
        inventory = pd.DataFrame(
            columns=["facility_id", "product_id", "period_id", "opening_m3", "closing_m3"]
        )
        consumption = pd.DataFrame(
            columns=["facility_id", "product_id", "period_id", "consumption_m3"]
        )
        objective_components = {}
        objective = None

    return {
        "objective": objective,
        "objective_components": objective_components,
        "harvest_decisions": harvest,
        "production": production,
        "flows": flows,
        "purchases": purchases,
        "inventory": inventory,
        "consumption": consumption,
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
    return pd.DataFrame(
        rows,
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
        ],
    )


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
    return pd.DataFrame(
        rows,
        columns=["option_id", "block_id", "system_id", "period_id", "product_id", "volume_m3"],
    )


def _extract_flows(model: pyo.ConcreteModel) -> pd.DataFrame:
    meta = model._tactical_meta
    periods = meta["periods"]
    arc_by_id = meta["arc_by_id"]
    rows: list[dict[str, Any]] = []
    for arc_id in meta["arcs"]:
        arc = arc_by_id[arc_id]
        volume = float(pyo.value(model.flow[arc_id]))
        if volume <= 1e-9:
            continue
        period = periods[arc.period_id]
        rows.append(
            {
                "arc_id": arc_id,
                "origin_id": arc.origin_id,
                "destination_id": arc.destination_id,
                "product_id": arc.product_id,
                "period_id": arc.period_id,
                "mode": arc.mode,
                "volume_m3": volume,
                "transport_cost": period.discount_factor * arc.cost_per_m3 * volume,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "arc_id",
            "origin_id",
            "destination_id",
            "product_id",
            "period_id",
            "mode",
            "volume_m3",
            "transport_cost",
        ],
    )


def _extract_purchases(model: pyo.ConcreteModel) -> pd.DataFrame:
    meta = model._tactical_meta
    periods = meta["periods"]
    supply_by_key = meta["supply_by_key"]
    rows: list[dict[str, Any]] = []
    for supply_key in meta["supplies"]:
        supply = supply_by_key[supply_key]
        volume = float(pyo.value(model.purchase[supply_key]))
        if volume <= 1e-9:
            continue
        period = periods[supply.period_id]
        rows.append(
            {
                "source_id": supply.source_id,
                "destination_id": supply.destination_id,
                "product_id": supply.product_id,
                "period_id": supply.period_id,
                "volume_m3": volume,
                "purchase_cost": period.discount_factor * supply.delivered_cost_per_m3 * volume,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "source_id",
            "destination_id",
            "product_id",
            "period_id",
            "volume_m3",
            "purchase_cost",
        ],
    )


def _extract_inventory(model: pyo.ConcreteModel) -> pd.DataFrame:
    meta = model._tactical_meta
    opening = meta["opening_inventory"]
    previous_period = meta["previous_period"]
    rows: list[dict[str, Any]] = []
    for facility_id, product_id, period_id in meta["facility_keys"]:
        closing = float(pyo.value(model.inventory[(facility_id, product_id, period_id)]))
        previous_id = previous_period[period_id]
        if previous_id is None:
            opening_value = opening.get((facility_id, product_id), 0.0)
        else:
            opening_value = float(
                pyo.value(model.inventory[(facility_id, product_id, previous_id)])
            )
        if closing <= 1e-9 and opening_value <= 1e-9:
            continue
        rows.append(
            {
                "facility_id": facility_id,
                "product_id": product_id,
                "period_id": period_id,
                "opening_m3": opening_value,
                "closing_m3": closing,
            }
        )
    return pd.DataFrame(
        rows,
        columns=["facility_id", "product_id", "period_id", "opening_m3", "closing_m3"],
    )


def _extract_consumption(model: pyo.ConcreteModel) -> pd.DataFrame:
    meta = model._tactical_meta
    rows: list[dict[str, Any]] = []
    for facility_id, product_id, period_id in meta["facility_keys"]:
        value = float(pyo.value(model.consumption[(facility_id, product_id, period_id)]))
        if value <= 1e-9:
            continue
        rows.append(
            {
                "facility_id": facility_id,
                "product_id": product_id,
                "period_id": period_id,
                "consumption_m3": value,
            }
        )
    return pd.DataFrame(
        rows,
        columns=["facility_id", "product_id", "period_id", "consumption_m3"],
    )


def _objective_components(
    model: pyo.ConcreteModel,
    harvest: pd.DataFrame,
    flows: pd.DataFrame,
    purchases: pd.DataFrame,
    consumption: pd.DataFrame,
    inventory: pd.DataFrame,
) -> dict[str, float]:
    meta = model._tactical_meta
    bundle: TacticalOperationalMilpBundle = meta["bundle"]
    periods = meta["periods"]
    fixed = float(harvest["fixed_cost"].sum()) if not harvest.empty else 0.0
    variable = float(harvest["variable_cost"].sum()) if not harvest.empty else 0.0
    transport = float(flows["transport_cost"].sum()) if not flows.empty else 0.0
    purchase = float(purchases["purchase_cost"].sum()) if not purchases.empty else 0.0
    total_cost = fixed + variable + transport + purchase

    product_value = 0.0
    for row in consumption.itertuples(index=False):
        demand = meta["demand_by_key"].get((row.facility_id, row.product_id, row.period_id))
        if demand is None or demand.value_per_m3 is None:
            continue
        product_value += (
            periods[row.period_id].discount_factor
            * demand.value_per_m3
            * cast(float, row.consumption_m3)
        )

    terminal_inventory_value = 0.0
    final_period_id = meta["final_period_id"]
    facilities = meta["facilities"]
    for row in inventory.itertuples(index=False):
        if row.period_id != final_period_id:
            continue
        facility = facilities[row.facility_id]
        value_per_m3 = (facility.terminal_inventory_value_per_m3 or {}).get(row.product_id)
        if value_per_m3 is None:
            continue
        terminal_inventory_value += (
            periods[row.period_id].discount_factor * value_per_m3 * cast(float, row.closing_m3)
        )

    profile = bundle.scenario.economics.objective_profile
    net_objective = (
        total_cost
        if profile == "min_discounted_delivered_cost"
        else product_value + terminal_inventory_value - total_cost
    )
    return {
        "harvest_fixed_cost": fixed,
        "harvest_variable_cost": variable,
        "transport_cost": transport,
        "purchase_cost": purchase,
        "total_cost": total_cost,
        "product_value": product_value,
        "terminal_inventory_value": terminal_inventory_value,
        "net_objective": net_objective,
    }


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
