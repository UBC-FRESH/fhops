"""Tests for the Phase II continuous-time scheduling model."""

from __future__ import annotations

import pytest

from fhops.hauling.flow import build_flow_problem, solve_flow
from fhops.hauling.network import (
    Truckload,
    build_schedule_problem,
    build_schedule_problem_from_loads,
)
from fhops.hauling.schedule import (
    simulate_plan,
    solve_schedule,
    validate_schedule,
)
from tests.hauling.test_flow import _scenario


def _load(
    load_id: str = "L1",
    *,
    block_id: str = "b1",
    yard_id: str = "y1",
    contractor_id: str = "c1",
    truck_type_id: str = "highway",
) -> Truckload:
    return Truckload(
        load_id=load_id,
        day=1,
        block_id=block_id,
        yard_id=yard_id,
        contractor_id=contractor_id,
        truck_type_id=truck_type_id,
        sorted=True,
        volume_m3=45.0,
    )


def test_single_load_schedule_and_simulator_parity() -> None:
    problem = build_schedule_problem_from_loads(_scenario(), [_load()], 1)
    result = solve_schedule(problem, time_limit=60)
    assert result.status == "optimal"
    assert result.objective == pytest.approx(110.0)
    assert result.fixed_cost == pytest.approx(0.0)
    assert result.variable_cost == pytest.approx(110.0)
    assert result.overtime_cost == pytest.approx(0.0)
    row = result.schedule.iloc[0]
    assert row["arrival_pickup"] == pytest.approx(20.0)
    assert row["pickup_start"] == pytest.approx(20.0)
    assert row["pickup_finish"] == pytest.approx(30.0)
    assert row["arrival_delivery"] == pytest.approx(80.0)
    assert row["delivery_finish"] == pytest.approx(90.0)
    assert row["truck_return_time"] == pytest.approx(110.0)
    assert validate_schedule(problem, result.schedule) == []

    simulated = simulate_plan(problem, result.plan)  # type: ignore[arg-type]
    merged = result.schedule.merge(simulated, on="load_id", suffixes=("_mip", "_sim"))
    for column in (
        "arrival_pickup",
        "pickup_start",
        "pickup_finish",
        "arrival_delivery",
        "delivery_start",
        "delivery_finish",
    ):
        assert merged[f"{column}_mip"].tolist() == pytest.approx(
            merged[f"{column}_sim"].tolist(), abs=1e-5
        )


def test_two_loads_one_truck_sequence() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(supply_sorted=90.0, demand_day_1=90.0),
        [_load("L1"), _load("L2")],
        1,
    )
    result = solve_schedule(problem, time_limit=60)
    assert result.status == "optimal"
    assert result.objective == pytest.approx(230.0)
    assert result.truck_summary["loads"].sum() == 2
    schedule = result.schedule.sort_values("load_order")
    assert schedule["load_order"].tolist() == [1, 2]
    assert schedule.iloc[0]["pickup_start"] == pytest.approx(20.0)
    assert schedule.iloc[1]["arrival_pickup"] == pytest.approx(140.0)
    assert schedule.iloc[1]["delivery_finish"] == pytest.approx(210.0)
    assert validate_schedule(problem, result.schedule) == []


def test_fixed_and_overtime_costs() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(
            travel_minutes=480.0,
            fixed_cost=100.0,
            variable_cost=1.0,
            overtime_cost=2.0,
        ),
        [_load()],
        1,
    )
    result = solve_schedule(problem, time_limit=60)
    assert result.status == "optimal"
    # Depot 20 + load 10 + travel 480 + unload 10 + return 20 = 540.
    assert result.truck_summary.iloc[0]["return_time"] == pytest.approx(540.0)
    assert result.truck_summary.iloc[0]["regular_minutes"] == pytest.approx(510.0)
    assert result.truck_summary.iloc[0]["overtime_minutes"] == pytest.approx(30.0)
    assert result.fixed_cost == pytest.approx(100.0)
    assert result.variable_cost == pytest.approx(510.0)
    assert result.overtime_cost == pytest.approx(60.0)
    assert result.objective == pytest.approx(670.0)


def test_infeasible_when_return_exceeds_the_day() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(travel_minutes=700.0),
        [_load()],
        1,
    )
    result = solve_schedule(problem, time_limit=60)
    assert result.status == "infeasible"


def test_load_with_no_compatible_truck_is_rejected() -> None:
    base = _scenario(contractor_count=2)
    assert base.hauling is not None
    config = base.hauling.model_copy(
        update={"trucks": [truck for truck in base.hauling.trucks if truck.contractor_id == "c1"]}
    )
    scenario = base.model_copy(update={"hauling": config})
    problem = build_schedule_problem_from_loads(scenario, [_load(contractor_id="c2")], 1)
    from fhops.hauling.schedule import build_schedule_model

    with pytest.raises(ValueError, match="no compatible truck"):
        build_schedule_model(problem)


def test_unknown_contractor_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown contractor_id=c9"):
        build_schedule_problem_from_loads(_scenario(), [_load(contractor_id="c9")], 1)


def test_unknown_truck_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown truck_type_id=offhighway"):
        build_schedule_problem_from_loads(_scenario(), [_load(truck_type_id="offhighway")], 1)


def test_validate_schedule_detects_loader_overlap() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(supply_sorted=90.0, demand_day_1=90.0),
        [_load("L1"), _load("L2")],
        1,
    )
    result = solve_schedule(problem, time_limit=60)
    schedule = result.schedule.copy()
    # Force both loads into the same pickup-loader window.
    schedule.loc[schedule["load_id"] == "L1", "pickup_start"] = 20.0
    schedule.loc[schedule["load_id"] == "L2", "pickup_start"] = 25.0
    schedule.loc[schedule["load_id"] == "L1", "pickup_finish"] = 30.0
    schedule.loc[schedule["load_id"] == "L2", "pickup_finish"] = 35.0
    violations = validate_schedule(problem, schedule)
    assert any("overlapping pickup service" in violation for violation in violations)


def test_build_from_phase_i_result() -> None:
    scenario = _scenario(supply_sorted=90.0, demand_day_1=90.0)
    flow = solve_flow(build_flow_problem(scenario), time_limit=60)
    assert flow.status == "optimal"
    problem = build_schedule_problem(scenario, flow, 1)
    assert len(problem.loads) == 2
    result = solve_schedule(problem, time_limit=60)
    assert result.status == "optimal"
    assert result.schedule["load_id"].nunique() == len(problem.loads)
    assert validate_schedule(problem, result.schedule) == []


def test_day_outside_horizon_is_rejected() -> None:
    scenario = _scenario()
    flow = solve_flow(build_flow_problem(scenario), time_limit=60)
    with pytest.raises(ValueError, match="outside the hauling horizon"):
        build_schedule_problem(scenario, flow, 2)
