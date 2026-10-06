"""Playback honours ``initial_state`` consistently with the MILP and heuristics (#91)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from fhops.evaluation import compute_kpis
from fhops.evaluation.playback import assignments_to_records
from fhops.model.milp.driver import solve_operational_milp
from fhops.optimization.heuristics.common import Schedule, _ensure_mobilisation_stats
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import (
    BlockInitialState,
    MachineInitialState,
    Problem,
    ScenarioInitialState,
    ScheduleLock,
)
from fhops.scenario.contract.models import ObjectiveWeights

from ._scenarios import chain_scenario

ASSIGNMENTS = pd.DataFrame(
    [
        {"machine_id": "F1", "block_id": "B1", "day": 1, "shift_id": "S1", "assigned": 1},
        {"machine_id": "S1", "block_id": "B1", "day": 1, "shift_id": "S1", "assigned": 1},
    ]
)

STATE = ScenarioInitialState(
    blocks=[BlockInitialState(block_id="B1", staged_inventory={"feller_buncher": 40.0})],
    machines=[
        MachineInitialState(machine_id="F1", last_block_id="B2"),
        MachineInitialState(machine_id="S1", last_block_id="B1"),
    ],
)


def test_playback_staged_inventory_and_boundary_mobilisation() -> None:
    plain = Problem.from_scenario(chain_scenario(mobilisation=True))
    stateful = Problem.from_scenario(chain_scenario(mobilisation=True, initial_state=STATE))

    plain_records = list(assignments_to_records(plain, ASSIGNMENTS))
    state_records = list(assignments_to_records(stateful, ASSIGNMENTS))
    by_machine = {record.machine_id: record for record in state_records}
    assert by_machine["F1"].mobilisation_cost == pytest.approx(30.0)
    assert by_machine["S1"].mobilisation_cost is None
    assert by_machine["S1"].production_units == pytest.approx(40.0)
    assert all(record.mobilisation_cost is None for record in plain_records)
    assert {r.machine_id: r.production_units for r in plain_records}["S1"] == pytest.approx(0.0)

    kpis = compute_kpis(stateful, ASSIGNMENTS)
    assert kpis["mobilisation_cost"] == pytest.approx(30.0)
    assert json.loads(str(kpis["mobilisation_cost_by_machine"])) == {"F1": 30.0}
    assert kpis["total_production"] == pytest.approx(40.0)
    assert "mobilisation_cost" not in compute_kpis(plain, ASSIGNMENTS)


def test_boundary_mobilisation_consistent_across_solvers() -> None:
    weights = ObjectiveWeights(production=1.0, mobilisation=1.0, transitions=0.0)
    lock = [
        ScheduleLock(machine_id="F1", block_id="B1", day=1),
        ScheduleLock(machine_id="S1", block_id="B1", day=1),
    ]

    def build(initial_state: ScenarioInitialState | None) -> Problem:
        return Problem.from_scenario(
            chain_scenario(
                mobilisation=True,
                objective_weights=weights,
                locked_assignments=lock,
                initial_state=initial_state,
            )
        )

    # Playback KPI.
    playback_cost = float(compute_kpis(build(STATE), ASSIGNMENTS)["mobilisation_cost"])

    # Heuristic mobilisation cache.
    pb = build(STATE)
    ctx = build_operational_problem(pb)
    schedule = Schedule(plan={"F1": {(1, "S1"): "B1"}, "S1": {(1, "S1"): "B1"}})
    _ensure_mobilisation_stats(schedule, ctx)
    heuristic_cost = sum(stats.cost for stats in schedule.mobilisation_cache.values())

    # MILP objective difference against the same state without machine positions (production is
    # identical because both machines are locked).
    def milp_objective(problem: Problem) -> float:
        milp_ctx = build_operational_problem(problem)
        result = solve_operational_milp(milp_ctx.bundle, solver="highs", context=milp_ctx)
        return float(result["objective"])

    no_position = ScenarioInitialState(blocks=STATE.blocks)
    milp_cost = milp_objective(build(no_position)) - milp_objective(build(STATE))

    assert playback_cost == pytest.approx(30.0)
    assert heuristic_cost == pytest.approx(30.0)
    assert milp_cost == pytest.approx(30.0)
