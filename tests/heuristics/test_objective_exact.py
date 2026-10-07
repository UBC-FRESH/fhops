"""The heuristic search score equals a fresh ``evaluate_schedule`` of the same plan (#131).

Before 1.0.1 the SA/ILS/Tabu score could exceed a fresh evaluation of the exported schedule:
operator candidates leave the sanitizer with an empty mobilisation cache, the repair pass marks only
the machines it changes as dirty, and ``_ensure_mobilisation_stats`` recomputed only the dirty
machines, so the unchanged machines' mobilisation and transitions were left out of the score.

These tests check, for random operator sequences (accepted and rejected moves) and for every
solver, that each score the search uses equals a fresh full evaluation of a cache-free copy of the
scored plan, and that the reported ``objective`` equals ``evaluate_schedule`` of the exported
assignments. Scenarios: tiny7, small21 and a three-shift scenario with mobilisation, day- and
shift-level locks, ``initial_state``, a blackout and an unavailable shift.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from functools import cache
from typing import Any

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from fhops.optimization.heuristics import common, ils, sa, tabu
from fhops.optimization.heuristics.common import (
    Schedule,
    _ensure_mobilisation_stats,
    _recompute_mobilisation_for,
    evaluate_schedule,
    generate_neighbors,
    init_greedy_schedule,
    resolve_objective_weight_overrides,
)
from fhops.optimization.heuristics.ils import _assignments_to_schedule
from fhops.optimization.heuristics.registry import OperatorRegistry
from fhops.optimization.operational_problem import (
    OperationalProblem,
    build_operational_problem,
    override_objective_weights,
)
from fhops.scenario.contract import (
    Block,
    BlockInitialState,
    CalendarEntry,
    Landing,
    Machine,
    MachineInitialState,
    Problem,
    ProductionRate,
    Scenario,
    ScenarioInitialState,
    ScheduleLock,
)
from fhops.scenario.contract.models import ObjectiveWeights, ShiftCalendarEntry
from fhops.scenario.io import load_scenario
from fhops.scheduling.mobilisation import BlockDistance, MachineMobilisation, MobilisationConfig
from fhops.scheduling.systems import HarvestSystem, SystemJob
from fhops.scheduling.timeline.models import BlackoutWindow, ShiftDefinition, TimelineConfig

TOL = 1e-9
OPERATORS = OperatorRegistry.from_defaults().names()


def multishift_scenario() -> Scenario:
    """Three shifts per day, 4-role chain, mobilisation, locks, initial state, blackout."""

    system = HarvestSystem(
        system_id="pipe",
        jobs=[
            SystemJob("felling", "feller_buncher", []),
            SystemJob("primary_transport", "grapple_skidder", ["felling"]),
            SystemJob("processing", "processor", ["primary_transport"]),
            SystemJob("loading", "loader", ["processing"]),
        ],
    )
    fleet = {
        "FB1": ("feller_buncher", 60.0),
        "FB2": ("feller_buncher", 40.0),
        "SK1": ("grapple_skidder", 50.0),
        "SK2": ("grapple_skidder", 45.0),
        "PR1": ("processor", 70.0),
        "LD1": ("loader", 90.0),
    }
    blocks = {"B1": ("L1", 400.0), "B2": ("L2", 300.0), "B3": ("L3", 350.0), "B4": ("L1", 250.0)}
    num_days = 5
    shifts = ("S1", "S2", "S3")
    distances = {("B1", "B2"): 300.0, ("B1", "B3"): 2500.0, ("B1", "B4"): 50.0}
    distances.update({("B2", "B3"): 800.0, ("B2", "B4"): 1800.0, ("B3", "B4"): 4000.0})
    return Scenario(
        name="objective-exact-multishift",
        num_days=num_days,
        blocks=[
            Block(id=bid, landing_id=lid, work_required=work, harvest_system_id="pipe")
            for bid, (lid, work) in blocks.items()
        ],
        machines=[Machine(id=mid, role=role) for mid, (role, _rate) in fleet.items()],
        landings=[Landing(id=lid, daily_capacity=2) for lid in ("L1", "L2", "L3")],
        calendar=[
            CalendarEntry(machine_id=mid, day=d, available=1)
            for mid in fleet
            for d in range(1, num_days + 1)
        ],
        shift_calendar=[
            ShiftCalendarEntry(
                machine_id=mid,
                day=d,
                shift_id=s,
                available=0 if (mid, d, s) == ("SK2", 2, "S2") else 1,
            )
            for mid in fleet
            for d in range(1, num_days + 1)
            for s in shifts
        ],
        production_rates=[
            ProductionRate(machine_id=mid, block_id=bid, rate=rate)
            for mid, (_role, rate) in fleet.items()
            for bid in blocks
        ],
        harvest_systems={"pipe": system},
        timeline=TimelineConfig(
            shifts=[ShiftDefinition(name=s, hours=8.0, shifts_per_day=1) for s in shifts],
            blackouts=[BlackoutWindow(start_day=4, end_day=4, reason="fire ban")],
        ),
        mobilisation=MobilisationConfig(
            machine_params=[
                MachineMobilisation(
                    machine_id=mid,
                    walk_cost_per_meter=0.02 * (index + 1),
                    move_cost_flat=150.0 + 10.0 * index,
                    walk_threshold_m=1000.0,
                    setup_cost=5.0 + index,
                )
                for index, mid in enumerate(fleet)
            ],
            distances=[
                BlockDistance(from_block=a, to_block=b, distance_m=d)
                for (x, y), d in distances.items()
                for a, b in ((x, y), (y, x))
            ],
        ),
        objective_weights=ObjectiveWeights(production=1.0, mobilisation=0.5, transitions=2.0),
        locked_assignments=[
            ScheduleLock(machine_id="FB2", block_id="B3", day=2),
            ScheduleLock(machine_id="PR1", block_id="B1", day=3, shift_id="S2"),
        ],
        initial_state=ScenarioInitialState(
            blocks=[
                BlockInitialState(
                    block_id="B1",
                    role_remaining={"feller_buncher": 250.0, "grapple_skidder": 320.0},
                    staged_inventory={"feller_buncher": 70.0, "grapple_skidder": 30.0},
                )
            ],
            machines=[
                MachineInitialState(machine_id="FB1", last_block_id="B2"),
                MachineInitialState(machine_id="SK1", last_block_id="B1"),
                MachineInitialState(machine_id="LD1", last_block_id="B3"),
            ],
        ),
    )


def _with_tiny7_extras(scenario: Scenario) -> Scenario:
    """tiny7 with a lock and an initial machine position on top of its mobilisation config."""

    machines = [machine.id for machine in scenario.machines]
    blocks = [block.id for block in scenario.blocks]
    return scenario.model_copy(
        update={
            "locked_assignments": [
                ScheduleLock(machine_id=machines[0], block_id=blocks[-1], day=3)
            ],
            "initial_state": ScenarioInitialState(
                machines=[MachineInitialState(machine_id=machines[1], last_block_id=blocks[-1])]
            ),
        }
    )


SCENARIOS: dict[str, Callable[[], Scenario]] = {
    "tiny7": lambda: load_scenario("examples/tiny7/scenario.yaml"),
    "tiny7_locks_initial_state": lambda: _with_tiny7_extras(
        load_scenario("examples/tiny7/scenario.yaml")
    ),
    "small21": lambda: load_scenario("examples/small21/scenario.yaml"),
    "multishift": multishift_scenario,
}


@cache
def _setup(name: str) -> tuple[Problem, OperationalProblem]:
    pb = Problem.from_scenario(SCENARIOS[name]())
    ctx = build_operational_problem(pb)
    overrides = resolve_objective_weight_overrides(pb, None)
    if overrides:
        ctx = override_objective_weights(ctx, overrides)
    return pb, ctx


def _plan_copy(sched: Schedule) -> dict[str, dict[tuple[int, str], str | None]]:
    return {machine: dict(slots) for machine, slots in sched.plan.items()}


def _fresh_score(pb: Problem, ctx: OperationalProblem, sched: Schedule) -> float:
    """Full evaluation of a cache-free copy; the copy's plan must not change (repair fixpoint)."""

    plan = _plan_copy(sched)
    fresh = Schedule(plan=_plan_copy(sched))
    score = evaluate_schedule(pb, fresh, ctx)
    assert fresh.plan == plan
    return score


def _single_operator_registry(name: str) -> OperatorRegistry:
    registry = OperatorRegistry.from_defaults()
    registry.configure({other: (1.0 if other == name else 0.0) for other in registry.names()})
    return registry


def test_mobilisation_cache_covers_machines_missing_from_cache() -> None:
    """Minimal reproduction: empty cache + one dirty machine must still charge every machine."""

    pb, ctx = _setup("tiny7")
    greedy = init_greedy_schedule(pb, ctx)
    evaluate_schedule(pb, greedy, ctx)
    expected = {m: (s.cost, s.transitions) for m, s in greedy.mobilisation_cache.items()}
    assert sum(cost for cost, _ in expected.values()) > 0.0

    # What the operator sanitizer + repair hand to evaluate_schedule: a plan-only schedule
    # with a subset of machines marked dirty.
    candidate = Schedule(plan=_plan_copy(greedy))
    candidate.dirty_machines = {pb.scenario.machines[0].id}
    _ensure_mobilisation_stats(candidate, ctx)
    actual = {m: (s.cost, s.transitions) for m, s in candidate.mobilisation_cache.items()}
    assert actual == expected
    assert not candidate.dirty_machines


def test_mobilisation_cache_drops_machines_not_in_plan() -> None:
    pb, ctx = _setup("tiny7")
    sched = init_greedy_schedule(pb, ctx)
    machine = pb.scenario.machines[0].id
    sched.mobilisation_cache["GHOST"] = sched.mobilisation_cache[machine]
    sched.dirty_machines.add("GHOST")
    _ensure_mobilisation_stats(sched, ctx)
    assert "GHOST" not in sched.mobilisation_cache
    assert "GHOST" not in sched.dirty_machines


@pytest.mark.parametrize("name", sorted(SCENARIOS))
@settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    moves=st.lists(st.sampled_from(OPERATORS), min_size=1, max_size=12),
    accept=st.lists(st.booleans(), min_size=12, max_size=12),
)
def test_random_operator_sequences_keep_score_exact(
    name: str, seed: int, moves: list[str], accept: list[bool]
) -> None:
    pb, ctx = _setup(name)
    rng = random.Random(seed)
    current = init_greedy_schedule(pb, ctx)
    current_score = evaluate_schedule(pb, current, ctx)
    assert abs(current_score - _fresh_score(pb, ctx, current)) <= TOL
    stats: dict[str, dict[str, float]] = {}
    for step, operator in enumerate(moves):
        registry = _single_operator_registry(operator)
        candidates = generate_neighbors(pb, current, registry, rng, stats, ctx, batch_size=1)
        for candidate in candidates:
            score = evaluate_schedule(pb, candidate, ctx)
            assert abs(score - _fresh_score(pb, ctx, candidate)) <= TOL, operator
            for machine_id in candidate.plan:
                cached = candidate.mobilisation_cache[machine_id]
                _recompute_mobilisation_for(candidate, machine_id, ctx)
                assert candidate.mobilisation_cache[machine_id] == cached
            if accept[step]:
                current, current_score = candidate, score
        # Re-scoring the kept schedule (accepted or not) reproduces its cached score.
        assert abs(evaluate_schedule(pb, current, ctx) - current_score) <= TOL
        assert abs(current_score - _fresh_score(pb, ctx, current)) <= TOL


class _ScoreAudit:
    """Wrap ``evaluate_schedule`` so every search score is checked against a fresh evaluation."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls = 0
        self.max_gap = 0.0
        original = common.evaluate_schedule

        def audited(
            pb: Problem,
            sched: Schedule,
            ctx: OperationalProblem,
            debug: dict[str, Any] | None = None,
            *,
            limit_repairs_to_dirty: bool = False,
        ) -> float:
            score = original(pb, sched, ctx, debug, limit_repairs_to_dirty=limit_repairs_to_dirty)
            plan = _plan_copy(sched)
            fresh = Schedule(plan=_plan_copy(sched))
            fresh_score = original(pb, fresh, ctx)
            assert fresh.plan == plan
            self.calls += 1
            self.max_gap = max(self.max_gap, abs(score - fresh_score))
            return score

        for module in (common, sa, ils, tabu):
            monkeypatch.setattr(module, "evaluate_schedule", audited)


def _exported_score(pb: Problem, ctx: OperationalProblem, assignments: pd.DataFrame) -> float:
    return evaluate_schedule(pb, _assignments_to_schedule(pb, assignments), ctx)


SOLVER_CASES = [
    ("sa", lambda pb: sa.solve_sa(pb, iters=80, seed=3)),
    ("sa_batched", lambda pb: sa.solve_sa(pb, iters=40, seed=5, batch_size=3)),
    ("ils", lambda pb: ils.solve_ils(pb, iters=6, seed=3, stall_limit=2)),
    ("tabu", lambda pb: tabu.solve_tabu(pb, iters=60, seed=3, batch_size=2)),
]


@pytest.mark.parametrize("name", ["tiny7_locks_initial_state", "small21", "multishift"])
@pytest.mark.parametrize(("solver", "run"), SOLVER_CASES, ids=[case[0] for case in SOLVER_CASES])
def test_solvers_score_and_report_fresh_evaluation(
    monkeypatch: pytest.MonkeyPatch, name: str, solver: str, run: Callable[[Problem], dict]
) -> None:
    pb, ctx = _setup(name)
    audit = _ScoreAudit(monkeypatch)
    result = run(pb)
    assert audit.calls > 0
    assert audit.max_gap <= TOL, solver
    monkeypatch.undo()
    assert abs(result["objective"] - _exported_score(pb, ctx, result["assignments"])) <= TOL
    assert result["meta"]["best_score"] == result["objective"]


def test_watch_debug_capture_reports_fresh_evaluation() -> None:
    pb, ctx = _setup("multishift")
    snapshots: list[Any] = []
    for run in (sa.solve_sa, ils.solve_ils, tabu.solve_tabu):
        result = run(pb, iters=10, seed=2, watch_sink=snapshots.append, watch_debug=True)
        assert abs(result["objective"] - _exported_score(pb, ctx, result["assignments"])) <= TOL
    assert snapshots


def test_ils_hybrid_mip_adoption_is_scored_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    pb, ctx = _setup("multishift")
    audit = _ScoreAudit(monkeypatch)
    result = ils.solve_ils(
        pb,
        iters=4,
        seed=1,
        stall_limit=1,
        hybrid_use_mip=True,
        hybrid_mip_time_limit=10,
    )
    assert result["meta"]["hybrid_mip"]
    assert audit.max_gap <= TOL
    monkeypatch.undo()
    assert abs(result["objective"] - _exported_score(pb, ctx, result["assignments"])) <= TOL


def test_local_repairs_report_fresh_evaluation() -> None:
    """``use_local_repairs`` scores are approximate; the reported objective is still exact."""

    pb, ctx = _setup("tiny7")
    for run in (sa.solve_sa, ils.solve_ils, tabu.solve_tabu):
        result = run(pb, iters=10, seed=4, use_local_repairs=True)
        assert abs(result["objective"] - _exported_score(pb, ctx, result["assignments"])) <= TOL


def test_tabu_initial_score_uses_full_repair_by_default() -> None:
    pb, _ctx = _setup("tiny7")
    tabu_result = tabu.solve_tabu(pb, iters=1, seed=1)
    sa_result = sa.solve_sa(pb, iters=1, seed=1)
    assert tabu_result["meta"]["initial_score"] == sa_result["meta"]["initial_score"]


def test_repair_keeps_idle_locked_slot() -> None:
    """A lock on a block without remaining demand stays in the plan (no lock penalty)."""

    pb, ctx = _setup("multishift")
    scenario = pb.scenario.model_copy(
        update={
            "locked_assignments": [ScheduleLock(machine_id="FB1", block_id="B1", day=5)],
            "initial_state": ScenarioInitialState(
                blocks=[BlockInitialState(block_id="B1", role_remaining={"feller_buncher": 0.0})]
            ),
        }
    )
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    sched = init_greedy_schedule(pb, ctx)
    score = evaluate_schedule(pb, sched, ctx)
    for shift_id in ("S1", "S2", "S3"):
        assert sched.plan["FB1"][(5, shift_id)] == "B1"
    assert abs(score - _fresh_score(pb, ctx, sched)) <= TOL
