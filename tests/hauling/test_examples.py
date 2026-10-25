"""Checks for the committed hauling example bundles."""

from __future__ import annotations

from fhops.hauling.flow import build_flow_problem
from fhops.scenario.io import load_scenario


def test_scale_example_dimensions() -> None:
    scenario = load_scenario("examples/hauling_scale/scenario.yaml")
    assert scenario.hauling is not None
    assert len(scenario.blocks) == 13
    assert len(scenario.hauling.sort_yards) == 3
    assert len(scenario.hauling.contractors) == 4
    assert len(scenario.hauling.trucks) == 60
    problem = build_flow_problem(scenario)
    assert problem.horizon_days == 2
    assert sum(problem.supply_sorted.values()) + sum(problem.supply_unsorted.values()) == 7200.0
    assert sum(problem.demand.values()) == 7200.0


def test_marine_example_dimensions_and_flow() -> None:
    from fhops.hauling.flow import solve_flow

    scenario = load_scenario("examples/hauling_marine/scenario.yaml")
    assert scenario.hauling is not None
    assert len(scenario.hauling.ports) == 2
    assert len(scenario.hauling.barges) == 1
    assert len(scenario.hauling.marine_routes) == 1
    problem = build_flow_problem(scenario)
    assert problem.has_marine()
    result = solve_flow(problem, time_limit=60)
    assert result.status == "optimal"
    assert result.marine_flows["water_m3"].sum() == 180.0
