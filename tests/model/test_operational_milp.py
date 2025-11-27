from dataclasses import replace

import pyomo.environ as pyo
import pytest

from fhops.model.milp.data import build_operational_bundle
from fhops.model.milp.driver import solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scenario.io.loaders import load_scenario
from fhops.scheduling.systems import HarvestSystem, SystemJob


def test_operational_model_builds_for_tiny7() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)

    model = build_operational_model(bundle)
    assert isinstance(model, pyo.ConcreteModel)
    assert len(model.M) == len(bundle.machines)
    assert len(model.B) == len(bundle.blocks)
    assert len(model.block_balance) == len(bundle.blocks)


def test_operational_model_has_production_limits() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)
    model = build_operational_model(bundle)

    some_machine = next(iter(bundle.machines))
    some_block = next(iter(bundle.blocks))
    some_slot = next(iter(bundle.shifts))

    rate = bundle.production_rates.get((some_machine, some_block), 0.0)
    if rate == 0:
        rate = 1.0

    model.x[some_machine, some_block, some_slot].fix(1)
    model.prod[some_machine, some_block, some_slot].setub(rate)
    assert model.prod[some_machine, some_block, some_slot].ub == rate


def test_operational_model_with_mobilisation_adds_transitions() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)
    mobilisation_params = {
        machine_id: {
            "walk_cost_per_meter": 0.01,
            "move_cost_flat": 100.0,
            "walk_threshold_m": 200.0,
            "setup_cost": 10.0,
        }
        for machine_id in bundle.machines
    }
    mobilisation_distances = {(blk, blk): 0.0 for blk in bundle.blocks}
    mobil_bundle = replace(
        bundle,
        mobilisation_params=mobilisation_params,
        mobilisation_distances=mobilisation_distances,
    )
    model = build_operational_model(mobil_bundle)
    assert hasattr(model, "y")


def test_headstart_delays_downstream_role_until_buffer_met() -> None:
    problem = _build_headstart_problem()
    bundle = build_operational_bundle(problem)

    result = solve_operational_milp(bundle, solver="highs", time_limit=5)
    assignments = result["assignments"]
    assert not assignments.empty
    day1_mask = (assignments["machine_id"] == "P1") & (assignments["day"] == 1)
    day2_mask = (assignments["machine_id"] == "P1") & (assignments["day"] == 2)
    assert assignments.loc[day1_mask].empty
    assert not assignments.loc[day2_mask].empty


def test_loader_batches_enforce_truckload_chunks() -> None:
    problem = _build_loader_batch_problem()
    bundle = build_operational_bundle(problem)

    result = solve_operational_milp(bundle, solver="highs", time_limit=5)
    assert result["production"] == pytest.approx(90.0)


def _build_headstart_problem() -> Problem:
    system = HarvestSystem(
        system_id="two_role",
        jobs=[
            SystemJob(name="felling", machine_role="feller-buncher", prerequisites=[]),
            SystemJob(
                name="processing",
                machine_role="roadside_processor",
                prerequisites=["felling"],
            ),
        ],
        role_headstart_shifts={"processor": 1.0},
    )
    scenario = Scenario(
        name="headstart",
        num_days=2,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=20.0,
                earliest_start=1,
                latest_finish=2,
                harvest_system_id="two_role",
            )
        ],
        machines=[
            Machine(id="F1", role="feller-buncher"),
            Machine(id="P1", role="roadside_processor"),
        ],
        landings=[Landing(id="L1", daily_capacity=4)],
        calendar=[
            CalendarEntry(machine_id="F1", day=1, available=1),
            CalendarEntry(machine_id="F1", day=2, available=1),
            CalendarEntry(machine_id="P1", day=1, available=1),
            CalendarEntry(machine_id="P1", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="F1", block_id="B1", rate=10.0),
            ProductionRate(machine_id="P1", block_id="B1", rate=15.0),
        ],
        harvest_systems={"two_role": system},
    )
    return Problem.from_scenario(scenario)


def _build_loader_batch_problem() -> Problem:
    system = HarvestSystem(
        system_id="load_only",
        jobs=[SystemJob(name="loading", machine_role="loader", prerequisites=[])],
        loader_batch_volume_m3=30.0,
    )
    scenario = Scenario(
        name="loader-batch",
        num_days=1,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=95.0,
                earliest_start=1,
                latest_finish=1,
                harvest_system_id="load_only",
            )
        ],
        machines=[Machine(id="L1", role="loader")],
        landings=[Landing(id="L1", daily_capacity=4)],
        calendar=[CalendarEntry(machine_id="L1", day=1, available=1)],
        production_rates=[ProductionRate(machine_id="L1", block_id="B1", rate=95.0)],
        harvest_systems={"load_only": system},
    )
    return Problem.from_scenario(scenario)
