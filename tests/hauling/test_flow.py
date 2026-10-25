"""Tests for the Phase I monthly flow model."""

from __future__ import annotations

import pytest

from fhops.hauling import (
    Contractor,
    ContractorBlock,
    Depot,
    DepotLeg,
    DriverPolicy,
    HaulArc,
    HaulingConfig,
    HaulingDemand,
    HaulingSupply,
    LoaderLocation,
    LoaderLocationKind,
    LogSort,
    SortYard,
    Truck,
    TruckType,
)
from fhops.hauling.flow import build_flow_problem, solve_flow
from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)


def _scenario(
    *,
    supply_sorted: float = 45.0,
    demand_day_1: float = 45.0,
    truck_count: int = 1,
    contractor_count: int = 1,
    contractor_blocks: list[ContractorBlock] | None = None,
    capacity_m3: float = 45.0,
    extra_block: bool = False,
    unsorted: bool = False,
    travel_minutes: float = 50.0,
    sorted_capacity_m3: float = 1000.0,
    fixed_cost: float = 0.0,
    variable_cost: float = 1.0,
    overtime_cost: float = 2.0,
) -> Scenario:
    contractors = [
        Contractor(id=f"c{index + 1}", preferred_daily_truckloads=1.0)
        for index in range(contractor_count)
    ]
    trucks = [
        Truck(
            id=f"c{contractor_index + 1}_h{truck_index + 1}",
            contractor_id=f"c{contractor_index + 1}",
            truck_type_id="highway",
        )
        for contractor_index in range(contractor_count)
        for truck_index in range(truck_count)
    ]
    config = HaulingConfig(
        planning_horizon_days=1,
        start_day=1,
        log_sorts=[LogSort(id="mixed" if unsorted else "saw", sorted=not unsorted)],
        contractors=contractors,
        truck_types=[
            TruckType(
                id="highway",
                capacity_m3=capacity_m3,
                fixed_cost=fixed_cost,
                variable_cost_per_minute=variable_cost,
                overtime_cost_per_minute=overtime_cost,
            )
        ],
        trucks=trucks,
        depots=[Depot(id="depot")],
        sort_yards=[
            SortYard(
                id="y1",
                unsorted_storage_m3=1000.0,
                sorted_processing_m3_per_day=sorted_capacity_m3,
                unsorted_processing_m3_per_day=1000.0,
                total_processing_m3_per_day=1000.0,
            )
        ],
        depot_legs=[
            DepotLeg(
                depot_id="depot",
                location_id="b1",
                truck_type_id="highway",
                travel_minutes=20.0,
            ),
            DepotLeg(
                depot_id="depot",
                location_id="y1",
                truck_type_id="highway",
                travel_minutes=20.0,
            ),
        ],
        loader_locations=[
            LoaderLocation(
                loader_id="loader_b1",
                location_id="b1",
                location_kind=LoaderLocationKind.PICKUP,
                service_minutes=10.0,
            ),
            LoaderLocation(
                loader_id="loader_y1",
                location_id="y1",
                location_kind=LoaderLocationKind.DELIVERY,
                service_minutes=10.0,
            ),
        ],
        supply=[
            HaulingSupply(
                block_id="b1",
                log_sort_id="mixed" if unsorted else "saw",
                sorted_m3=0.0 if unsorted else supply_sorted,
                unsorted_m3=supply_sorted if unsorted else 0.0,
            )
        ],
        demand=[
            HaulingDemand(
                yard_id="y1",
                log_sort_id="mixed" if unsorted else "saw",
                day=1,
                volume_m3=demand_day_1,
            )
        ],
        haul_arcs=[
            HaulArc(
                block_id="b1",
                yard_id="y1",
                truck_type_id="highway",
                travel_minutes=travel_minutes,
            )
        ],
        contractor_blocks=contractor_blocks or [],
        driver_policy=DriverPolicy(regular_minutes=510.0, max_overtime_minutes=150.0),
        roadside_inventory_penalty_per_m3=100.0,
    )
    return Scenario(
        name="flow-test",
        num_days=1,
        schema_version="1.1.0",
        blocks=[
            Block(id="b1", landing_id="l1", work_required=supply_sorted),
            *([Block(id="b2", landing_id="l1", work_required=0.0)] if extra_block else []),
        ],
        machines=[
            Machine(id="loader_b1", role="loader"),
            Machine(id="loader_y1", role="loader"),
        ],
        landings=[Landing(id="l1", daily_capacity=2)],
        calendar=[
            CalendarEntry(machine_id="loader_b1", day=1, available=1),
            CalendarEntry(machine_id="loader_y1", day=1, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="loader_b1", block_id="b1", rate=supply_sorted)
        ],
        hauling=config,
    )


def test_problem_cycle_and_cost_are_derived_from_the_contract() -> None:
    scenario = _scenario()
    problem = build_flow_problem(scenario)
    # 2 * 50 travel + 10 pickup + 10 delivery = 120 minutes; $1/min -> $120 per load.
    assert problem.cycle_minutes[("b1", "y1", "highway")] == pytest.approx(120.0)
    assert problem.transport_cost[("b1", "y1", "highway")] == pytest.approx(120.0)
    assert problem.fleet_count[("c1", "highway")] == 1


def test_one_load_matches_the_hand_computed_cost() -> None:
    result = solve_flow(build_flow_problem(_scenario()))
    assert result.status == "optimal"
    assert result.cost_objective == pytest.approx(120.0)
    assert result.workload_objective == pytest.approx(0.0)
    assert len(result.flows) == 1
    row = result.flows.iloc[0]
    assert row["sorted_m3"] == pytest.approx(45.0)
    assert row["unsorted_m3"] == pytest.approx(0.0)
    assert result.truckloads["total_truckloads"].sum() == 1
    assert result.yard_inventory.iloc[0]["water_inventory_m3"] == pytest.approx(0.0)
    assert result.yard_inventory.iloc[0]["demand_m3"] == pytest.approx(45.0)
    assert result.block_inventory.iloc[0]["sorted_inventory_m3"] == pytest.approx(0.0)


def test_two_loads_cost_two_cycles() -> None:
    result = solve_flow(build_flow_problem(_scenario(supply_sorted=90.0, demand_day_1=90.0)))
    assert result.status == "optimal"
    assert result.cost_objective == pytest.approx(240.0)
    assert result.truckloads["total_truckloads"].sum() == 2


def test_infeasible_when_demand_exceeds_supply() -> None:
    result = solve_flow(build_flow_problem(_scenario(supply_sorted=45.0, demand_day_1=100.0)))
    assert result.status == "infeasible"
    assert result.cost_objective is None


def test_incompatible_contractor_makes_the_supply_undeliverable() -> None:
    feasible = solve_flow(
        build_flow_problem(
            _scenario(contractor_blocks=[ContractorBlock(contractor_id="c1", block_id="b1")])
        )
    )
    assert feasible.status == "optimal"

    infeasible = solve_flow(
        build_flow_problem(
            _scenario(
                extra_block=True,
                contractor_blocks=[ContractorBlock(contractor_id="c1", block_id="b2")],
            )
        )
    )
    assert infeasible.status == "infeasible"


def test_goal_with_zero_workload_weight_reproduces_the_cost_optimum() -> None:
    problem = build_flow_problem(_scenario(supply_sorted=90.0, demand_day_1=90.0))
    cost = solve_flow(problem)
    goal = solve_flow(
        problem,
        objective="goal",
        goals=(cost.cost_objective or 0.0, 0.0),
        preferred={"c1": 2.0},
        weights=(1.0, 0.0),
    )
    assert goal.status == "optimal"
    assert goal.cost_objective == pytest.approx(cost.cost_objective)
    assert goal.goal_deviations["cost"] == pytest.approx(0.0, abs=1e-6)


def test_workload_objective_balances_two_contractors() -> None:
    scenario = _scenario(
        supply_sorted=90.0,
        demand_day_1=90.0,
        contractor_count=2,
        contractor_blocks=[
            ContractorBlock(contractor_id="c1", block_id="b1"),
            ContractorBlock(contractor_id="c2", block_id="b1"),
        ],
    )
    result = solve_flow(
        build_flow_problem(scenario),
        objective="workload",
        preferred={"c1": 1.0, "c2": 1.0},
    )
    assert result.status == "optimal"
    assert result.workload_objective == pytest.approx(0.0)
    loads = result.contractor_workload.set_index("contractor_id")["truckloads"]
    assert loads["c1"] == pytest.approx(1.0)
    assert loads["c2"] == pytest.approx(1.0)


def test_goal_solve_derives_goals_and_preferred_from_the_cost_plan() -> None:
    result = solve_flow(
        build_flow_problem(_scenario(supply_sorted=90.0, demand_day_1=90.0)),
        objective="goal",
        weights=(1.0, 0.5),
    )
    assert result.status == "optimal"
    assert result.goal1 == pytest.approx(240.0)
    assert result.goal2 == pytest.approx(0.0)
    assert result.preferred_truckloads["c1"] == pytest.approx(2.0)
    assert result.goal_deviations["cost"] >= 0.0
    assert result.goal_deviations["workload"] >= 0.0


def test_unsorted_supply_is_hauled_and_processed() -> None:
    result = solve_flow(
        build_flow_problem(_scenario(unsorted=True, supply_sorted=90.0, demand_day_1=45.0))
    )
    assert result.status == "optimal"
    assert result.flows["unsorted_m3"].sum() == pytest.approx(90.0)
    assert result.truckloads["unsorted_truckloads"].sum() == 2
    inventory = result.yard_inventory
    assert inventory["processed_m3"].sum() + inventory[
        "unsorted_inventory_m3"
    ].sum() == pytest.approx(90.0)
    assert inventory["water_inventory_m3"].iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_sorted_processing_capacity_is_enforced() -> None:
    result = solve_flow(
        build_flow_problem(
            _scenario(supply_sorted=45.0, demand_day_1=45.0, sorted_capacity_m3=40.0)
        )
    )
    assert result.status == "infeasible"


def test_fleet_capacity_is_enforced() -> None:
    # One truck, one 300-minute cycle, 510 regular minutes: one load per day, but demand is two.
    result = solve_flow(
        build_flow_problem(_scenario(supply_sorted=90.0, demand_day_1=90.0, travel_minutes=140.0))
    )
    assert result.status == "infeasible"


def test_example_scenario_solves() -> None:
    from fhops.scenario.io import load_scenario

    scenario = load_scenario("examples/hauling/scenario.yaml")
    result = solve_flow(build_flow_problem(scenario), time_limit=60)
    assert result.status == "optimal"
    assert not result.flows.empty
    assert not result.truckloads.empty
    assert not result.contractor_workload.empty


def test_goal_programming_trades_cost_against_contractor_balance() -> None:
    base = _scenario(
        supply_sorted=90.0,
        demand_day_1=90.0,
        contractor_count=2,
        contractor_blocks=[
            ContractorBlock(contractor_id="c1", block_id="b1"),
            ContractorBlock(contractor_id="c2", block_id="b1"),
        ],
    )
    assert base.hauling is not None
    config = base.hauling.model_copy(
        update={
            "truck_types": [
                TruckType(
                    id="highway",
                    capacity_m3=45.0,
                    variable_cost_per_minute=1.0,
                ),
                TruckType(
                    id="offhighway",
                    capacity_m3=45.0,
                    variable_cost_per_minute=2.0,
                ),
            ],
            "trucks": [
                Truck(id="c1_h1", contractor_id="c1", truck_type_id="highway"),
                Truck(id="c2_o1", contractor_id="c2", truck_type_id="offhighway"),
            ],
            "haul_arcs": [
                HaulArc(
                    block_id="b1",
                    yard_id="y1",
                    truck_type_id="highway",
                    travel_minutes=50.0,
                ),
                HaulArc(
                    block_id="b1",
                    yard_id="y1",
                    truck_type_id="offhighway",
                    travel_minutes=50.0,
                ),
            ],
        }
    )
    scenario = base.model_copy(update={"hauling": config})
    problem = build_flow_problem(scenario)

    cost = solve_flow(problem)
    assert cost.status == "optimal"
    assert cost.cost_objective == pytest.approx(240.0)

    balanced = solve_flow(
        problem,
        objective="workload",
        preferred={"c1": 1.0, "c2": 1.0},
    )
    assert balanced.status == "optimal"
    assert balanced.workload_objective == pytest.approx(0.0)
    assert balanced.cost_objective == pytest.approx(360.0)

    cost_first = solve_flow(
        problem,
        objective="goal",
        goals=(240.0, 0.0),
        preferred={"c1": 1.0, "c2": 1.0},
        weights=(1.0, 0.0),
    )
    assert cost_first.cost_objective == pytest.approx(240.0)

    balance_first = solve_flow(
        problem,
        objective="goal",
        goals=(240.0, 0.0),
        preferred={"c1": 1.0, "c2": 1.0},
        weights=(0.0, 1.0),
    )
    assert balance_first.workload_objective == pytest.approx(0.0)
    assert balance_first.cost_objective == pytest.approx(360.0)


def test_summary_reports_the_key_metrics() -> None:
    from fhops.hauling.flow import summarize_flow_result

    result = solve_flow(build_flow_problem(_scenario()))
    summary = summarize_flow_result(result)
    assert "status: optimal" in summary
    assert "cost_objective: 120.000" in summary
    assert "truckloads: sorted=1, unsorted=0, total=1" in summary
    assert "delivered_m3: 45.000" in summary
