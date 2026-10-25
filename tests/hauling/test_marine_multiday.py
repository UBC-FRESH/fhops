"""Regression tests for multi-day marine barge cycles (FHOPS #196)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.hauling import Barge, Truck
from fhops.hauling.flow import build_flow_problem, solve_flow
from fhops.scenario.io import load_scenario

FIXTURE = Path(__file__).resolve().parents[2] / "examples/hauling_marine_multiday/scenario.yaml"


def test_multiday_fixture_exposes_separate_arrival_and_occupancy_days() -> None:
    """Cargo arrival must not be confused with the full round-trip occupancy."""
    scenario = load_scenario(FIXTURE)
    problem = build_flow_problem(scenario)
    lane = problem.marine_lanes["quatsino_ladysmith_yard"]
    assert lane.barge_cycle_minutes == pytest.approx(3955.0)
    assert lane.arrival_lag_days == 4
    assert lane.occupancy_days == 8
    assert lane.arrival_lag_days < lane.occupancy_days


def test_multiday_marine_voyage_is_optimal() -> None:
    """One barge should arrive on day 5 and deliver on demand day 8."""
    scenario = load_scenario(FIXTURE)
    result = solve_flow(build_flow_problem(scenario), time_limit=60)
    assert result.status == "optimal"
    assert result.cost_objective is not None
    assert result.cost_objective > 0.0

    flow = result.marine_flows.iloc[0]
    assert flow["day"] == 1
    assert flow["arrival_day"] == 5
    assert flow["water_m3"] == pytest.approx(10000.0)
    assert flow["delivery_road_m3"] == pytest.approx(10000.0)

    trip = result.barge_trips.iloc[0]
    assert trip["day"] == 1
    assert trip["arrival_day"] == 5
    assert trip["transit_days"] == 4
    assert trip["occupancy_days"] == 8
    assert trip["barge_trips"] == pytest.approx(1.0)

    delivery = result.marine_truckloads[result.marine_truckloads["leg"] == "delivery"].iloc[0]
    assert delivery["day"] == 5

    ladysmith_day_5 = result.port_inventory[
        (result.port_inventory["port_id"] == "ladysmith") & (result.port_inventory["day"] == 5)
    ].iloc[0]
    assert ladysmith_day_5["inbound_m3"] == pytest.approx(10000.0)

    yard_day_5 = result.yard_inventory[result.yard_inventory["day"] == 5].iloc[0]
    assert yard_day_5["water_inventory_m3"] == pytest.approx(10000.0)


def test_demand_before_arrival_is_infeasible() -> None:
    """The voyage cannot satisfy demand before cargo reaches Ladysmith."""
    scenario = load_scenario(FIXTURE)
    assert scenario.hauling is not None
    scenario.hauling.demand = [
        demand.model_copy(update={"day": 1}) for demand in scenario.hauling.demand
    ]
    result = solve_flow(build_flow_problem(scenario), time_limit=60)
    assert result.status == "infeasible"


def test_two_barges_can_cover_a_double_volume_voyage() -> None:
    """Two barges should be able to cover two full loads in the same window."""
    scenario = load_scenario(FIXTURE)
    assert scenario.hauling is not None
    config = scenario.hauling
    scenario.num_days = 16
    config.planning_horizon_days = 16
    scenario.blocks[0].work_required = 20000.0
    config.supply[0].sorted_m3 = 20000.0
    config.demand[0].day = 16
    config.demand[0].volume_m3 = 20000.0
    config.barges.append(Barge(id="c1_b2", contractor_id="c1", barge_type_id="log_barge"))
    for index in range(61, 121):
        config.trucks.append(
            Truck(
                id=f"c1_h{index}",
                contractor_id="c1",
                truck_type_id="highway",
            )
        )
    result = solve_flow(build_flow_problem(scenario), time_limit=60)
    assert result.status == "optimal"
    assert result.marine_flows["water_m3"].sum() == pytest.approx(20000.0)
    assert result.barge_trips["barge_trips"].sum() == pytest.approx(2.0)
