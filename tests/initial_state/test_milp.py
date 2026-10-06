"""Operational MILP honours ``initial_state`` and ``locked_assignments`` (#91)."""

from __future__ import annotations

import pandas as pd
import pyomo.environ as pyo
import pytest

from fhops.model.milp.driver import _apply_incumbent_start, solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import (
    BlockInitialState,
    MachineInitialState,
    Problem,
    Scenario,
    ScenarioInitialState,
    ScheduleLock,
)
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scenario.io import load_scenario

from ._scenarios import chain_scenario, solo_two_shift_scenario


def _solve(scenario: Scenario, **kwargs) -> dict:
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    result = solve_operational_milp(ctx.bundle, solver="highs", context=ctx, **kwargs)
    assert result["termination_condition"].lower() == "optimal"
    return result


def _assigned(result: dict) -> set[tuple[str, str, int, str]]:
    frame: pd.DataFrame = result["assignments"]
    frame = frame[frame["assigned"] > 0]
    return {
        (str(row.machine_id), str(row.block_id), int(row.day), str(row.shift_id))
        for row in frame.itertuples(index=False)
    }


def _staged(volume: float, *, remaining: float | None = None) -> ScenarioInitialState:
    return ScenarioInitialState(
        blocks=[
            BlockInitialState(
                block_id="B1",
                staged_inventory={"feller_buncher": volume},
                role_remaining={} if remaining is None else {"feller_buncher": remaining},
            )
        ]
    )


def test_initial_staged_inventory_feeds_first_slot() -> None:
    # One-day horizon: without staged felled wood the skidder (terminal) cannot produce.
    baseline = _solve(chain_scenario())
    assert baseline["objective"] == pytest.approx(-40.0)

    staged = _solve(chain_scenario(initial_state=_staged(40.0)))
    assert staged["objective"] == pytest.approx(40.0)
    frame = staged["assignments"]
    skid = frame[(frame["machine_id"] == "S1") & (frame["block_id"] == "B1")]
    assert skid["production"].sum() == pytest.approx(40.0)


def test_first_slot_inventory_start_is_min_over_upstream() -> None:
    model = build_operational_model(
        build_operational_problem(
            Problem.from_scenario(chain_scenario(initial_state=_staged(25.0)))
        ).bundle
    )
    meta = getattr(model, "_warm_start_meta")
    assert meta["initial_inventory_start"][("grapple_skidder", "B1")] == pytest.approx(25.0)
    assert meta["initial_inventory_start"][("grapple_skidder", "B2")] == pytest.approx(0.0)
    constraint = model.inventory_start_eq["grapple_skidder", "B1", 1, "S1"]
    assert pyo.value(constraint.upper) == pytest.approx(25.0)


def test_role_remaining_caps_upstream_output() -> None:
    # Two days, B1 needs 100. Staged 20 feeds day 1; the feller may add at most 30 more.
    capped = _solve(
        chain_scenario(num_days=2, work_b1=100.0, initial_state=_staged(20.0, remaining=30.0))
    )
    uncapped = _solve(chain_scenario(num_days=2, work_b1=100.0, initial_state=_staged(20.0)))

    def delivered(result: dict) -> float:
        frame = result["assignments"]
        return float(frame[frame["machine_id"] == "S1"]["production"].sum())

    def felled(result: dict) -> float:
        frame = result["assignments"]
        return float(frame[frame["machine_id"] == "F1"]["production"].sum())

    assert delivered(capped) == pytest.approx(50.0)
    assert felled(capped) <= 30.0 + 1e-6
    assert delivered(uncapped) == pytest.approx(60.0)
    assert capped["objective"] == pytest.approx(0.0)
    assert uncapped["objective"] == pytest.approx(20.0)


def test_last_block_charges_first_slot_boundary_move() -> None:
    weights = ObjectiveWeights(production=1.0, mobilisation=1.0, transitions=0.5)
    lock = [ScheduleLock(machine_id="F1", block_id="B1", day=1)]
    common = dict(mobilisation=True, objective_weights=weights, locked_assignments=lock)

    free = _solve(chain_scenario(**common))
    moved = _solve(
        chain_scenario(
            initial_state=ScenarioInitialState(
                machines=[MachineInitialState(machine_id="F1", last_block_id="B2")]
            ),
            **common,
        )
    )
    stayed = _solve(
        chain_scenario(
            initial_state=ScenarioInitialState(
                machines=[MachineInitialState(machine_id="F1", last_block_id="B1")]
            ),
            **common,
        )
    )
    # setup 10 + 200 m × 0.1 = 30 mobilisation, plus 0.5 × 1 transition.
    assert free["objective"] - moved["objective"] == pytest.approx(30.5)
    assert stayed["objective"] == pytest.approx(free["objective"])


def test_day_lock_enforced_on_tiny7() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    unlocked = _assigned(_solve(scenario))
    # Lock H1 on day 3 to a block the unlocked optimum does not use for that slot.
    target = "B01" if ("H1", "B02", 3, "S1") in unlocked else "B02"
    assert ("H1", target, 3, "S1") not in unlocked
    locked = scenario.model_copy(
        update={"locked_assignments": [ScheduleLock(machine_id="H1", block_id=target, day=3)]}
    )
    result = _assigned(_solve(locked))
    assert ("H1", target, 3, "S1") in result
    assert not any(e[0] == "H1" and e[2] == 3 and e[1] != target for e in result)


def test_shift_lock_only_fixes_its_slot() -> None:
    unlocked = _assigned(_solve(solo_two_shift_scenario()))
    assert unlocked == {("F1", "B1", 1, "S1"), ("F1", "B1", 1, "S2")}

    shift_locked = _assigned(
        _solve(
            solo_two_shift_scenario(
                locked_assignments=[
                    ScheduleLock(machine_id="F1", block_id="B2", day=1, shift_id="S2")
                ]
            )
        )
    )
    assert shift_locked == {("F1", "B1", 1, "S1"), ("F1", "B2", 1, "S2")}

    day_locked = _assigned(
        _solve(
            solo_two_shift_scenario(
                locked_assignments=[ScheduleLock(machine_id="F1", block_id="B2", day=1)]
            )
        )
    )
    assert day_locked == {("F1", "B2", 1, "S1"), ("F1", "B2", 1, "S2")}


def test_warm_start_respects_locks_and_initial_inventory() -> None:
    scenario = solo_two_shift_scenario(
        locked_assignments=[ScheduleLock(machine_id="F1", block_id="B2", day=1, shift_id="S2")]
    )
    ctx = build_operational_problem(Problem.from_scenario(scenario))
    model = build_operational_model(ctx.bundle)
    getattr(model, "_warm_start_meta")["operational_problem"] = ctx
    incumbent = pd.DataFrame(
        [
            {"machine_id": "F1", "block_id": "B1", "day": 1, "shift_id": "S1", "assigned": 1},
            {"machine_id": "F1", "block_id": "B1", "day": 1, "shift_id": "S2", "assigned": 1},
        ]
    )
    assert _apply_incumbent_start(model, incumbent) == 2
    assert model.x["F1", "B1", (1, "S1")].value == 1
    assert model.x["F1", "B2", (1, "S2")].value == 1
    assert model.x["F1", "B1", (1, "S2")].value == 0
    # The seeded point satisfies the lock constraints.
    for constraint in model.locked_assignment.values():
        assert pyo.value(constraint.body) == pytest.approx(pyo.value(constraint.upper))

    staged_ctx = build_operational_problem(
        Problem.from_scenario(chain_scenario(num_days=2, initial_state=_staged(40.0)))
    )
    staged_model = build_operational_model(staged_ctx.bundle)
    getattr(staged_model, "_warm_start_meta")["operational_problem"] = staged_ctx
    staged_incumbent = pd.DataFrame(
        [{"machine_id": "S1", "block_id": "B1", "day": 1, "shift_id": "S1", "assigned": 1}]
    )
    _apply_incumbent_start(staged_model, staged_incumbent)
    assert staged_model.inventory_start["grapple_skidder", "B1", (1, "S1")].value == pytest.approx(
        40.0
    )
    assert staged_model.prod["S1", "B1", (1, "S1")].value == pytest.approx(40.0)
    assert staged_model.inventory["grapple_skidder", "B1", (1, "S1")].value == pytest.approx(0.0)
