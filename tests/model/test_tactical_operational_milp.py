"""Regression tests for the TOPM-inspired tactical–operational harvest MILP."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.model.milp.tactical_operational import (
    DemandBasis,
    TacticalHarvestMode,
    build_tactical_operational_bundle,
    solve_tactical_operational_milp,
    tactical_bundle_from_dict,
    tactical_bundle_to_dict,
)
from fhops.planning import load_tactical_operational_scenario

TOPM_MINI = (
    Path(__file__).parents[1]
    / "fixtures"
    / "tactical_operational"
    / "topm-mini"
    / "specification.yaml"
)


def _solve(
    mode: TacticalHarvestMode = TacticalHarvestMode.SEMI_CONTINUOUS, scenario_path=TOPM_MINI
):
    scenario = load_tactical_operational_scenario(scenario_path)
    bundle = build_tactical_operational_bundle(scenario, harvest_mode=mode)
    replayed = tactical_bundle_from_dict(tactical_bundle_to_dict(bundle))
    return solve_tactical_operational_milp(replayed, solver="highs", time_limit=30, gap=0.0)


def test_topm_mini_semi_continuous_economic_dispatch() -> None:
    result = _solve(TacticalHarvestMode.SEMI_CONTINUOUS)

    assert result["termination_condition"].lower() == "optimal"
    assert result["objective"] == pytest.approx(24130.0)
    assert result["objective_components"]["harvest_fixed_cost"] == pytest.approx(180.0)
    assert result["objective_components"]["harvest_variable_cost"] == pytest.approx(18000.0)
    assert result["objective_components"]["transport_cost"] == pytest.approx(5950.0)
    assert result["objective_components"]["purchase_cost"] == pytest.approx(0.0)

    harvest = result["harvest_decisions"].set_index("option_id")
    assert harvest.loc["B1__ground_fb_skid__Y1-P1", "harvested_area_ha"] == pytest.approx(6.0)
    assert harvest.loc["B2__ground_fb_skid__Y1-P1", "harvested_area_ha"] == pytest.approx(
        2.7777777778
    )
    assert "B3__ground_fb_skid__Y1-P1" not in harvest.index

    production = result["production"]
    sawlog = production.loc[production["product_id"] == "sawlog", "volume_m3"].sum()
    pulp = production.loc[production["product_id"] == "pulp", "volume_m3"].sum()
    assert sawlog == pytest.approx(730.0)
    assert pulp == pytest.approx(203.3333333333)

    flows = result["flows"]
    sawlog_flow = flows.loc[flows["product_id"] == "sawlog", "volume_m3"].sum()
    pulp_flow = flows.loc[flows["product_id"] == "pulp", "volume_m3"].sum()
    assert sawlog_flow == pytest.approx(730.0)
    assert pulp_flow == pytest.approx(160.0)

    inventory = result["inventory"].set_index(["facility_id", "product_id", "period_id"])
    assert inventory.loc[("mill_saw", "sawlog", "Y1-P1"), "closing_m3"] == pytest.approx(0.0)
    assert inventory.loc[("mill_pulp", "pulp", "Y1-P1"), "closing_m3"] == pytest.approx(0.0)


def test_continuous_mode_relaxes_minimum_cut() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    payload = scenario.to_dict()
    payload["facility_demand"] = [
        {
            "facility_id": "mill_saw",
            "product_id": "sawlog",
            "period_id": "Y1-P1",
            "minimum_m3": 100.0,
            "target_m3": 100.0,
            "maximum_m3": 100.0,
        },
        {
            "facility_id": "mill_pulp",
            "product_id": "pulp",
            "period_id": "Y1-P1",
            "minimum_m3": 0.0,
            "target_m3": 0.0,
            "maximum_m3": 0.0,
        },
    ]
    scenario = scenario.model_validate(payload)
    bundle = build_tactical_operational_bundle(
        scenario,
        harvest_mode=TacticalHarvestMode.CONTINUOUS,
        demand_basis=DemandBasis.TARGET,
    )
    result = solve_tactical_operational_milp(bundle, solver="highs", time_limit=30)

    assert result["termination_condition"].lower() == "optimal"
    harvest = result["harvest_decisions"].set_index("option_id")
    area = harvest.loc["B2__ground_fb_skid__Y1-P1", "harvested_area_ha"]
    assert area == pytest.approx(50.0 / 90.0)
    assert area < 1.0


def test_semi_continuous_rejects_positive_area_below_minimum() -> None:
    result = _solve(TacticalHarvestMode.SEMI_CONTINUOUS)
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    options = {option.option_id: option for option in scenario.harvest_system_options}

    for row in result["harvest_decisions"].itertuples(index=False):
        area = float(row.harvested_area_ha)
        if area <= 0:
            continue
        assert area >= options[row.option_id].min_area_ha


def test_discounted_profit_objective_profile() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    payload = scenario.to_dict()
    payload["facility_demand"][0]["value_per_m3"] = 60.0
    payload["facility_demand"][1]["value_per_m3"] = 25.0
    payload["economics"] = {
        "currency": "CAD",
        "base_year": 2026,
        "discount_rate_per_year": 0.0,
        "objective_profile": "max_discounted_profit",
    }
    scenario = scenario.model_validate(payload)
    bundle = build_tactical_operational_bundle(scenario)
    result = solve_tactical_operational_milp(bundle, solver="highs", time_limit=30)

    assert result["termination_condition"].lower() == "optimal"
    components = result["objective_components"]
    assert components["product_value"] == pytest.approx(51300.0)
    assert components["total_cost"] == pytest.approx(24130.0)
    assert result["objective"] == pytest.approx(27170.0)


def test_external_supply_covers_delivered_shortfall() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    payload = scenario.to_dict()
    for option in payload["harvest_system_options"]:
        option["eligible"] = option["option_id"] == "B1__ground_fb_skid__Y1-P1"
    payload["facility_demand"] = [
        {
            "facility_id": "mill_saw",
            "product_id": "sawlog",
            "period_id": "Y1-P1",
            "minimum_m3": 580.0,
            "target_m3": 580.0,
            "maximum_m3": 580.0,
        },
        {
            "facility_id": "mill_pulp",
            "product_id": "pulp",
            "period_id": "Y1-P1",
            "minimum_m3": 0.0,
            "target_m3": 0.0,
            "maximum_m3": 0.0,
        },
    ]
    scenario = scenario.model_validate(payload)
    bundle = build_tactical_operational_bundle(scenario)
    result = solve_tactical_operational_milp(bundle, solver="highs", time_limit=30)

    assert result["termination_condition"].lower() == "optimal"
    purchases = result["purchases"]
    assert len(purchases) == 1
    assert purchases.iloc[0]["volume_m3"] == pytest.approx(50.0)
    assert result["objective_components"]["purchase_cost"] == pytest.approx(2250.0)


def test_inventory_carries_between_periods() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    payload = scenario.to_dict()
    for option in payload["harvest_system_options"]:
        option["eligible"] = option["option_id"] in {
            "B1__ground_fb_skid__Y1-P1",
            "B1__ctl__Y1-P2",
        }
    payload["facility_demand"] = [
        {
            "facility_id": "mill_saw",
            "product_id": "sawlog",
            "period_id": "Y1-P1",
            "minimum_m3": 400.0,
            "target_m3": 400.0,
            "maximum_m3": 400.0,
        },
        {
            "facility_id": "mill_saw",
            "product_id": "sawlog",
            "period_id": "Y1-P2",
            "minimum_m3": 380.0,
            "target_m3": 380.0,
            "maximum_m3": 380.0,
        },
        {
            "facility_id": "mill_pulp",
            "product_id": "pulp",
            "period_id": "Y1-P1",
            "minimum_m3": 0.0,
            "target_m3": 0.0,
            "maximum_m3": 0.0,
        },
        {
            "facility_id": "mill_pulp",
            "product_id": "pulp",
            "period_id": "Y1-P2",
            "minimum_m3": 0.0,
            "target_m3": 0.0,
            "maximum_m3": 0.0,
        },
    ]
    payload["transport_arcs"].append(
        {
            "arc_id": "B1__mill_saw__truck__Y1-P2",
            "origin_id": "B1",
            "destination_id": "mill_saw",
            "product_id": "sawlog",
            "mode": "truck",
            "period_id": "Y1-P2",
            "cost_per_m3": 7.0,
            "capacity_m3": 500.0,
        }
    )
    scenario = scenario.model_validate(payload)
    bundle = build_tactical_operational_bundle(scenario)
    result = solve_tactical_operational_milp(bundle, solver="highs", time_limit=30)

    assert result["termination_condition"].lower() == "optimal"
    inventory = result["inventory"].set_index(["facility_id", "product_id", "period_id"])
    assert inventory.loc[("mill_saw", "sawlog", "Y1-P1"), "closing_m3"] == pytest.approx(130.0)
    assert inventory.loc[("mill_saw", "sawlog", "Y1-P2"), "opening_m3"] == pytest.approx(130.0)
    assert inventory.loc[("mill_saw", "sawlog", "Y1-P2"), "closing_m3"] == pytest.approx(0.0)


def test_whole_block_mode_uses_operable_area() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    payload = scenario.to_dict()
    payload["facility_demand"] = [
        {
            "facility_id": "mill_saw",
            "product_id": "sawlog",
            "period_id": "Y1-P1",
            "minimum_m3": 240.0,
            "target_m3": 240.0,
            "maximum_m3": 240.0,
        },
        {
            "facility_id": "mill_pulp",
            "product_id": "pulp",
            "period_id": "Y1-P1",
            "minimum_m3": 80.0,
            "target_m3": 80.0,
            "maximum_m3": 80.0,
        },
    ]
    scenario = scenario.model_validate(payload)
    bundle = build_tactical_operational_bundle(
        scenario,
        harvest_mode=TacticalHarvestMode.WHOLE_BLOCK,
        demand_basis=DemandBasis.TARGET,
    )
    result = solve_tactical_operational_milp(bundle, solver="highs", time_limit=30)

    assert result["termination_condition"].lower() == "optimal"
    harvest = result["harvest_decisions"].set_index("option_id")
    assert harvest.loc["B3__ground_fb_skid__Y1-P1", "harvested_area_ha"] == pytest.approx(4.0)
