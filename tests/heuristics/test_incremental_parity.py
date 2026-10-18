"""P10 parity: the block-separable scorer equals the full scorer.

For each example scenario, the test scores the greedy starting schedule and a few schedules reached
by random moves, and asserts ``score_separable`` matches ``_score_plan`` and every component.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.optimization.heuristics.common import (
    _repair_schedule_cover_blocks,
    _score_plan,
    init_greedy_schedule,
)
from fhops.optimization.heuristics.incremental import score_separable
from fhops.optimization.heuristics.registry import OperatorRegistry
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

ROOT = Path(__file__).resolve().parents[2]
LADDER = ["tiny7", "small21", "med42", "large84"]


def _moved_schedules(pb: Problem, ctx, base, count: int) -> list:
    """Return ``base`` plus ``count`` schedules reached by the real neighbour generator."""
    import random

    from fhops.optimization.heuristics.common import generate_neighbors

    rng = random.Random(7)
    registry = OperatorRegistry.from_defaults()
    operator_stats: dict[str, dict[str, float]] = {}
    out = [base]
    current = base
    for _ in range(count):
        neighbours = generate_neighbors(pb, current, registry, rng, operator_stats, ctx)
        if not neighbours:
            break
        current = neighbours[0]
        out.append(current)
    return out


@pytest.mark.parametrize("name", LADDER)
def test_separable_matches_full(name: str) -> None:
    scenario = load_scenario(str(ROOT / "examples" / name / "scenario.yaml"))
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    base = init_greedy_schedule(pb, ctx)
    _repair_schedule_cover_blocks(pb, base, ctx, fill_voids=True)

    for sched in _moved_schedules(pb, ctx, base, 5):
        full = _score_plan(pb, sched, ctx, None)
        sep, _ = score_separable(pb, sched, ctx)
        assert sep == pytest.approx(full, abs=1e-9), name


@pytest.mark.parametrize("name", LADDER)
def test_evaluator_matches_full_incrementally(name: str) -> None:
    """The cached evaluator matches the full scorer on every candidate of a move chain."""
    from fhops.optimization.heuristics.incremental import SeparableEvaluator, slot_diff

    scenario = load_scenario(str(ROOT / "examples" / name / "scenario.yaml"))
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    base = init_greedy_schedule(pb, ctx)
    _repair_schedule_cover_blocks(pb, base, ctx, fill_voids=True)
    evaluator = SeparableEvaluator(pb, ctx)
    assert evaluator.build(base) == pytest.approx(_score_plan(pb, base, ctx, None), abs=1e-9)
    current = base
    for candidate in _moved_schedules(pb, ctx, base, 5)[1:]:
        changed = slot_diff(evaluator.last, candidate)
        incremental = evaluator.score_after_move(candidate, changed)
        assert incremental == pytest.approx(_score_plan(pb, candidate, ctx, None), abs=1e-9), name
        current = candidate
    del current


def _plan_copy(sched) -> dict:
    return {machine: dict(slots) for machine, slots in sched.plan.items()}


@pytest.mark.parametrize("name", ["tiny7", "small21", "med42"])
def test_repair_resume_matches_full(name: str) -> None:
    """A resumed repair equals a full repair for a cell cleared at the resume slot."""
    from fhops.optimization.heuristics.common import Schedule

    scenario = load_scenario(str(ROOT / "examples" / name / "scenario.yaml"))
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    base = init_greedy_schedule(pb, ctx)
    _repair_schedule_cover_blocks(pb, base, ctx, fill_voids=True, snapshot=True)
    snapshots = base.repair_state.snapshots
    assert len(snapshots) == len(ctx.shift_keys)

    unchanged = Schedule(plan=_plan_copy(base))
    _repair_schedule_cover_blocks(
        pb, unchanged, ctx, fill_voids=True, resume=(snapshots, 0), snapshot=True
    )
    assert unchanged.plan == base.plan
    assert len(unchanged.repair_state.snapshots) == len(snapshots)

    for start in {0, len(ctx.shift_keys) // 2, len(ctx.shift_keys) - 1}:
        slot = ctx.shift_keys[start]
        machine = next(m for m in base.plan if base.plan[m].get(slot) is not None)
        candidate = Schedule(plan=_plan_copy(base))
        candidate.plan[machine][slot] = None
        reference = Schedule(plan=_plan_copy(candidate))
        _repair_schedule_cover_blocks(pb, reference, ctx, fill_voids=True)
        resumed = Schedule(plan=_plan_copy(candidate))
        _repair_schedule_cover_blocks(
            pb, resumed, ctx, fill_voids=True, resume=(snapshots, start), snapshot=True
        )
        assert resumed.plan == reference.plan, (name, start)
        assert len(resumed.repair_state.snapshots) == len(snapshots)


def test_sa_incremental_repair_parity() -> None:
    """``solve_sa`` with the incremental repair matches the full-repair run exactly."""
    from fhops.optimization.heuristics import solve_sa

    scenario = load_scenario(str(ROOT / "examples" / "small21" / "scenario.yaml"))
    pb = Problem.from_scenario(scenario)
    full = solve_sa(pb, iters=50, seed=42)
    incremental = solve_sa(pb, iters=50, seed=42, incremental_repair=True)
    assert incremental["objective"] == pytest.approx(full["objective"], abs=1e-9)
