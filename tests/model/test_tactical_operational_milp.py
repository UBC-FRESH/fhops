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
    assert result["objective"] == pytest.approx(19320.0)
    assert result["objective_components"]["fixed_cost"] == pytest.approx(180.0)
    assert result["objective_components"]["variable_cost"] == pytest.approx(19140.0)

    harvest = result["harvest_decisions"].set_index("option_id")
    assert harvest.loc["B2__ground_fb_skid__Y1-P1", "harvested_area_ha"] == pytest.approx(4.0)
    assert harvest.loc["B1__ground_fb_skid__Y1-P1", "harvested_area_ha"] == pytest.approx(5.25)
    assert "B3__ground_fb_skid__Y1-P1" not in harvest.index

    production = result["production"]
    sawlog = production.loc[production["product_id"] == "sawlog", "volume_m3"].sum()
    pulp = production.loc[production["product_id"] == "pulp", "volume_m3"].sum()
    assert sawlog == pytest.approx(780.0)
    assert pulp == pytest.approx(225.0)


def test_continuous_mode_relaxes_minimum_cut() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    payload = scenario.to_dict()
    payload["facility_demand"] = [
        {
            "facility_id": "mill_saw",
            "product_id": "sawlog",
            "period_id": "Y1-P1",
            "minimum_m3": 50.0,
            "target_m3": 50.0,
            "maximum_m3": 60.0,
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
