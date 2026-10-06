"""Sequencing tracker and heuristics honour ``initial_state`` and shift locks (#91)."""

from __future__ import annotations

import pytest

from fhops.evaluation.sequencing import build_sequencing_tracker
from fhops.optimization.heuristics import solve_sa
from fhops.optimization.heuristics.common import (
    Schedule,
    _ensure_mobilisation_stats,
    evaluate_schedule,
    init_greedy_schedule,
)
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import (
    BlockInitialState,
    MachineInitialState,
    Problem,
    ScenarioInitialState,
    ScheduleLock,
)
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scheduling.systems import HarvestSystem, SystemJob

from ._scenarios import chain_scenario, solo_two_shift_scenario

HEADSTART_SYSTEM = HarvestSystem(
    system_id="chain",
    jobs=[
        SystemJob("felling", "feller_buncher", []),
        SystemJob("primary_transport", "grapple_skidder", ["felling"]),
    ],
    role_headstart_shifts={"grapple_skidder": 2.0},
)


def _block_state(**kwargs) -> ScenarioInitialState:
    return ScenarioInitialState(blocks=[BlockInitialState(block_id="B1", **kwargs)])


def test_tracker_defaults_match_v100() -> None:
    tracker = build_sequencing_tracker(Problem.from_scenario(chain_scenario()))
    assert dict(tracker.role_inventory) == {}
    assert dict(tracker.role_counts_total) == {}
    assert tracker.role_remaining[("B1", "feller_buncher")] == pytest.approx(40.0)
    result = tracker.process(1, "S1", "B1", 40.0)
    assert result.production_units == pytest.approx(0.0)
    assert result.violation_reason == "missing_prereq"


def test_tracker_staged_inventory_feeds_first_day() -> None:
    scenario = chain_scenario(initial_state=_block_state(staged_inventory={"feller_buncher": 40.0}))
    tracker = build_sequencing_tracker(Problem.from_scenario(scenario))
    result = tracker.process(1, "S1", "B1", 40.0)
    assert result.production_units == pytest.approx(40.0)
    assert result.violation_reason is None
    assert result.block_completed
    assert tracker.role_inventory[("B1", "feller_buncher")] == pytest.approx(0.0)
    assert tracker.delivered_total == pytest.approx(40.0)


def test_tracker_role_remaining_caps_upstream() -> None:
    scenario = chain_scenario(
        work_b1=100.0, initial_state=_block_state(role_remaining={"feller_buncher": 30.0})
    )
    tracker = build_sequencing_tracker(Problem.from_scenario(scenario))
    assert tracker.process(1, "F1", "B1", 50.0).production_units == pytest.approx(30.0)
    assert tracker.process(2, "F1", "B1", 50.0).production_units == pytest.approx(0.0)


def test_tracker_headstart_seeded_by_staged_inventory() -> None:
    # Head-start buffers are staged volume (MILP E8, #109): 2 shifts x 50 m³ feller rate = 100 m³.
    # Carried-in shift counts no longer satisfy the buffer; staged inventory does.
    def make(staged: float, counts: dict[str, int]):
        scenario = chain_scenario(
            work_b1=200.0,
            initial_state=_block_state(
                staged_inventory={"feller_buncher": staged}, role_shift_counts=counts
            ),
        ).model_copy(update={"harvest_systems": {"chain": HEADSTART_SYSTEM}})
        return build_sequencing_tracker(Problem.from_scenario(scenario))

    without = make(40.0, {}).process(1, "S1", "B1", 40.0)
    assert without.violation_reason == "missing_prereq"
    with_counts = make(40.0, {"feller_buncher": 2}).process(1, "S1", "B1", 40.0)
    assert with_counts.violation_reason == "missing_prereq"
    with_volume = make(100.0, {}).process(1, "S1", "B1", 40.0)
    assert with_volume.violation_reason is None


def test_greedy_seed_uses_initial_role_remaining() -> None:
    scenario = chain_scenario(
        initial_state=_block_state(
            role_remaining={"feller_buncher": 0.0}, staged_inventory={"feller_buncher": 40.0}
        )
    )
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    assert ctx.role_work_required[("B1", "feller_buncher")] == 0.0
    schedule = init_greedy_schedule(pb, ctx)
    assert all(block is None for block in schedule.plan["F1"].values())
    assert schedule.plan["S1"][(1, "S1")] == "B1"


def test_sa_uses_initial_state() -> None:
    base = solve_sa(Problem.from_scenario(chain_scenario()), iters=50, seed=1)
    staged = solve_sa(
        Problem.from_scenario(
            chain_scenario(initial_state=_block_state(staged_inventory={"feller_buncher": 40.0}))
        ),
        iters=50,
        seed=1,
    )
    assert base["objective"] < 0
    assert staged["objective"] == pytest.approx(40.0)
    rows = staged["assignments"]
    assert ((rows["machine_id"] == "S1") & (rows["block_id"] == "B1") & (rows["day"] == 1)).any()


def test_evaluate_schedule_charges_boundary_move() -> None:
    weights = ObjectiveWeights(production=1.0, mobilisation=1.0, transitions=0.5)
    lock = [ScheduleLock(machine_id="F1", block_id="B1", day=1)]

    def score(initial_state: ScenarioInitialState | None) -> tuple[float, Schedule]:
        scenario = chain_scenario(
            mobilisation=True,
            objective_weights=weights,
            locked_assignments=lock,
            initial_state=initial_state,
        )
        pb = Problem.from_scenario(scenario)
        ctx = build_operational_problem(pb)
        schedule = Schedule(plan={"F1": {(1, "S1"): "B1"}, "S1": {(1, "S1"): None}})
        return evaluate_schedule(pb, schedule, ctx), schedule

    free_score, free_sched = score(None)
    moved_score, moved_sched = score(
        ScenarioInitialState(machines=[MachineInitialState(machine_id="F1", last_block_id="B2")])
    )
    assert free_sched.mobilisation_cache["F1"].cost == pytest.approx(0.0)
    assert moved_sched.mobilisation_cache["F1"].cost == pytest.approx(30.0)
    assert moved_sched.mobilisation_cache["F1"].transitions == pytest.approx(1.0)
    assert free_score - moved_score == pytest.approx(30.5)


def test_mobilisation_stats_without_state_unchanged() -> None:
    scenario = chain_scenario(num_days=2, work_b2=40.0, mobilisation=True)
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    schedule = Schedule(plan={"F1": {(1, "S1"): "B2", (2, "S1"): "B1"}, "S1": {}})
    _ensure_mobilisation_stats(schedule, ctx)
    assert schedule.mobilisation_cache["F1"].cost == pytest.approx(30.0)
    assert schedule.mobilisation_cache["F1"].transitions == pytest.approx(1.0)


def test_heuristic_shift_lock_only_pins_its_slot() -> None:
    scenario = solo_two_shift_scenario(
        locked_assignments=[ScheduleLock(machine_id="F1", block_id="B2", day=1, shift_id="S2")]
    )
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    assert ctx.lock_for("F1", 1, "S2") == "B2"
    assert ctx.lock_for("F1", 1, "S1") is None
    schedule = init_greedy_schedule(pb, ctx)
    assert schedule.plan["F1"][(1, "S2")] == "B2"
    assert schedule.plan["F1"][(1, "S1")] == "B1"
    sanitizer = ctx.build_sanitizer(Schedule)
    cleaned = sanitizer(Schedule(plan={"F1": {(1, "S1"): "B1", (1, "S2"): "B1"}}))
    assert cleaned.plan["F1"] == {(1, "S1"): "B1", (1, "S2"): "B2"}
    result = solve_sa(pb, iters=30, seed=3)
    rows = result["assignments"]
    locked_rows = rows[(rows["day"] == 1) & (rows["shift_id"] == "S2")]
    assert list(locked_rows["block_id"]) == ["B2"]
