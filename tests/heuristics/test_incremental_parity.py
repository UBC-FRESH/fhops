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
