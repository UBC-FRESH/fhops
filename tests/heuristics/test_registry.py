"""Tests for the heuristic operator registry."""

from __future__ import annotations

import random

from fhops.optimization.heuristics import OperatorContext, OperatorRegistry, Schedule
from fhops.optimization.heuristics.registry import MoveOperator, SwapOperator
from fhops.optimization.heuristics.common import generate_neighbors
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem, Scenario


def _dummy_problem() -> Problem:
    scenario = Scenario(
        name="dummy",
        num_days=1,
        blocks=[],
        machines=[],
        landings=[],
        calendar=[],
        production_rates=[],
    )
    return Problem.from_scenario(scenario)


def _dummy_schedule() -> Schedule:
    return Schedule(plan={})


def test_registry_defaults_expose_swap_and_move():
    registry = OperatorRegistry.from_defaults()
    names = {op.name for op in registry.enabled()}
    assert {"swap", "move"}.issubset(names)


def test_configure_updates_weights_and_disables():
    registry = OperatorRegistry.from_defaults()
    registry.configure({"swap": 0.0, "move": 2.0})
    enabled = list(registry.enabled())
    assert all(op.name != "swap" for op in enabled)
    move = next(op for op in enabled if op.name == "move")
    assert move.weight == 2.0


def test_enabled_iterator_uses_sanitizer_context():
    registry = OperatorRegistry.from_defaults([SwapOperator(), MoveOperator()])
    context = OperatorContext(
        problem=_dummy_problem(),
        schedule=_dummy_schedule(),
        sanitizer=lambda schedule: schedule,
        rng=random,
    )
    for operator in registry.enabled():
        result = operator.apply(context)
        # With empty schedules and no machines, operators may yield None
        assert result is None or isinstance(result, Schedule)


def test_neighbors_batch_limit():
    registry = OperatorRegistry.from_defaults()
    context = OperatorContext(
        problem=_dummy_problem(),
        schedule=_dummy_schedule(),
        sanitizer=lambda schedule: schedule,
        rng=random,
    )
    ctx = build_operational_problem(context.problem)
    neighbours = generate_neighbors(
        context.problem,
        context.schedule,
        registry,
        context.rng,
        {},
        ctx,
        batch_size=2,
    )
    assert len(neighbours) <= 2
