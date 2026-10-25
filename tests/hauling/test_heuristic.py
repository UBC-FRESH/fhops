"""Tests for the Phase III simulated-annealing scheduler."""

from __future__ import annotations

import random

import pytest

from fhops.hauling.flow import build_flow_problem, solve_flow
from fhops.hauling.heuristic import (
    SAConfig,
    decode_routes,
    evaluate_routes,
    initial_solution,
    neighbor_solution,
    solve_sa,
    summarize_sa_result,
)
from fhops.hauling.network import (
    Truckload,
    build_schedule_problem,
    build_schedule_problem_from_loads,
)
from fhops.hauling.schedule import solve_schedule, validate_schedule
from tests.hauling.test_flow import _scenario


def _load(load_id: str, *, contractor_id: str = "c1") -> Truckload:
    return Truckload(
        load_id=load_id,
        day=1,
        block_id="b1",
        yard_id="y1",
        contractor_id=contractor_id,
        truck_type_id="highway",
        sorted=True,
        volume_m3=45.0,
    )


def test_config_carries_the_thesis_defaults() -> None:
    config = SAConfig()
    assert config.initial_temperature == pytest.approx(300.0)
    assert config.min_temperature_ratio == pytest.approx(0.0005)
    assert config.cooling_rate == pytest.approx(0.95)
    assert config.iterations_per_temperature == 90


def test_decode_routes_builds_spt_loader_orders() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(supply_sorted=90.0, demand_day_1=90.0),
        [_load("L1"), _load("L2")],
        1,
    )
    plan = decode_routes(problem, {"c1_h1": ("L1", "L2")})
    assert plan.pickup_order["loader_b1"] == ("L1", "L2")
    assert plan.delivery_order["loader_y1"] == ("L1", "L2")
    assert plan.pickup_loader == {"L1": "loader_b1", "L2": "loader_b1"}


def test_decode_routes_rejects_missing_and_duplicate_loads() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(supply_sorted=90.0, demand_day_1=90.0),
        [_load("L1"), _load("L2")],
        1,
    )
    with pytest.raises(ValueError, match="missing loads"):
        decode_routes(problem, {"c1_h1": ("L1",)})
    with pytest.raises(ValueError, match="more than once"):
        decode_routes(problem, {"c1_h1": ("L1", "L1", "L2")})


def test_evaluate_one_load_matches_the_mip_cost() -> None:
    problem = build_schedule_problem_from_loads(_scenario(), [_load("L1")], 1)
    mip = solve_schedule(problem, time_limit=60)
    evaluation = evaluate_routes(problem, {"c1_h1": ("L1",)})
    assert evaluation.objective == pytest.approx(mip.objective)
    assert evaluation.violation_minutes == pytest.approx(0.0)


def test_sa_matches_the_mip_on_two_loads_one_truck() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(supply_sorted=90.0, demand_day_1=90.0),
        [_load("L1"), _load("L2")],
        1,
    )
    mip = solve_schedule(problem, time_limit=60)
    result = solve_sa(
        problem,
        SAConfig(iterations_per_temperature=10, max_iterations=200, seed=42),
    )
    assert result.status == "feasible"
    assert result.objective == pytest.approx(mip.objective)
    assert validate_schedule(problem, result.schedule) == []


def test_sa_matches_the_mip_on_the_example_day() -> None:
    scenario = _scenario(supply_sorted=90.0, demand_day_1=90.0, contractor_count=2)
    flow = solve_flow(build_flow_problem(scenario), time_limit=60)
    problem = build_schedule_problem(scenario, flow, 1)
    mip = solve_schedule(problem, time_limit=60)
    result = solve_sa(
        problem,
        SAConfig(iterations_per_temperature=10, max_iterations=200, seed=7),
    )
    assert result.status == "feasible"
    assert result.objective == pytest.approx(mip.objective, rel=0.15)
    assert validate_schedule(problem, result.schedule) == []


def test_sa_is_deterministic_for_a_fixed_seed() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(supply_sorted=90.0, demand_day_1=90.0),
        [_load("L1"), _load("L2")],
        1,
    )
    config = SAConfig(iterations_per_temperature=10, max_iterations=100, seed=123)
    first = solve_sa(problem, config)
    second = solve_sa(problem, config)
    assert first.objective == pytest.approx(second.objective)
    assert first.iterations == second.iterations
    assert first.accepted == second.accepted


def test_initial_solution_assigns_every_load() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(supply_sorted=90.0, demand_day_1=90.0),
        [_load("L1"), _load("L2")],
        1,
    )
    routes = initial_solution(problem, random.Random(1))
    assigned = [load_id for route in routes.values() for load_id in route]
    assert sorted(assigned) == ["L1", "L2"]


def test_neighbour_keeps_every_load_and_compatibility() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(supply_sorted=90.0, demand_day_1=90.0),
        [_load("L1"), _load("L2")],
        1,
    )
    rng = random.Random(3)
    routes = initial_solution(problem, rng)
    for _ in range(20):
        routes, _operator = neighbor_solution(problem, routes, rng, SAConfig())
        assigned = [load_id for route in routes.values() for load_id in route]
        assert sorted(assigned) == ["L1", "L2"]
        for truck_id, route in routes.items():
            for load_id in route:
                load = problem.load_by_id(load_id)
                assert truck_id in {truck.id for truck in problem.compatible_trucks(load)}


def test_overtime_violation_is_penalized() -> None:
    problem = build_schedule_problem_from_loads(
        _scenario(travel_minutes=700.0),
        [_load("L1")],
        1,
    )
    evaluation = evaluate_routes(
        problem,
        {"c1_h1": ("L1",)},
        SAConfig(overtime_violation_penalty_per_minute=100.0),
    )
    assert evaluation.violation_minutes > 0
    assert evaluation.violation_cost > 0
    assert evaluation.objective > evaluation.variable_cost


def test_summary_reports_the_search() -> None:
    problem = build_schedule_problem_from_loads(_scenario(), [_load("L1")], 1)
    result = solve_sa(
        problem,
        SAConfig(iterations_per_temperature=5, max_iterations=20, seed=4),
    )
    summary = summarize_sa_result(result)
    assert "status: feasible" in summary
    assert "iterations:" in summary
    assert "objective:" in summary
    assert "loads: 1" in summary
