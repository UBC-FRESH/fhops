"""Operator sanitizer preview and heuristic work bounds (#151).

After #140 the heuristics became several times slower on scenarios with a binding hard landing
capacity (synthetic-small SA 3×): block insertion, cross exchange and mobilisation shake build and
sanitize a full candidate for every try until one survives the sanitizer, and with a hard landing
capacity most tries are rejected (synthetic-small: about 400 full sanitizer passes per SA
iteration). :class:`~fhops.optimization.operational_problem.SanitizerPreview` decides a try from
the edited slots alone, so only accepted tries build a candidate. These tests pin the preview to
the real sanitizer and bound the per-iteration work so the regression cannot return silently.
"""

from __future__ import annotations

import random
from itertools import combinations

import pytest

import fhops.optimization.heuristics.registry as registry_module
from fhops.optimization.heuristics import solve_sa
from fhops.optimization.heuristics.common import Schedule
from fhops.optimization.heuristics.registry import (
    BlockInsertionOperator,
    CoverageInjectionOperator,
    CrossExchangeOperator,
    MobilisationShakeOperator,
    OperatorContext,
    _clone_schedule,
    _locked_assignments,
    _plan_equals,
    _production_rates,
    _set_slot,
    _shuffle,
    _shuffle_with_getrandbits,
    _window_allows,
)
from fhops.optimization.operational_problem import (
    OperationalProblem,
    build_operational_problem,
    override_objective_weights,
)
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)
from fhops.scenario.contract.models import ScheduleLock
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems import HarvestSystem, SystemJob
from fhops.scheduling.timeline.models import BlackoutWindow, ShiftDefinition, TimelineConfig

SYNTHETIC_SMALL = "examples/synthetic/small/scenario.yaml"
BLOCKS = ("B1", "B2", "B3", "B4")
MACHINES = (("F1", "feller_buncher"), ("F2", "feller_buncher"), ("K1", "grapple_skidder"))


def _problem(capacity: int) -> Problem:
    """Two shifts a day, two landings, roles, day/shift locks, a calendar gap and a blackout."""

    system = HarvestSystem(
        system_id="fk",
        jobs=[
            SystemJob("felling", "feller_buncher", []),
            SystemJob("primary_transport", "grapple_skidder", ["felling"]),
        ],
    )
    days = 6
    scenario = Scenario(
        name="sanitizer-preview",
        num_days=days,
        blocks=[
            Block(
                id=block_id,
                landing_id="L1" if index < 2 else "L2",
                work_required=300.0,
                harvest_system_id="fk" if index != 3 else None,
            )
            for index, block_id in enumerate(BLOCKS)
        ],
        machines=[Machine(id=machine_id, role=role) for machine_id, role in MACHINES],
        landings=[
            Landing(id="L1", daily_capacity=capacity),
            Landing(id="L2", daily_capacity=1),
        ],
        calendar=[
            CalendarEntry(
                machine_id=machine_id,
                day=day,
                available=0 if (machine_id, day) == ("F2", 3) else 1,
            )
            for machine_id, _role in MACHINES
            for day in range(1, days + 1)
        ],
        production_rates=[
            ProductionRate(machine_id=machine_id, block_id=block_id, rate=50.0)
            for machine_id, _role in MACHINES
            for block_id in BLOCKS
        ],
        harvest_systems={"fk": system},
        locked_assignments=[
            ScheduleLock(machine_id="F1", block_id="B1", day=1),
            ScheduleLock(machine_id="K1", block_id="B3", day=4, shift_id="S2"),
        ],
        timeline=TimelineConfig(
            shifts=[ShiftDefinition(name=name, hours=8, shifts_per_day=1) for name in ("S1", "S2")],
            blackouts=[BlackoutWindow(start_day=5, end_day=5, reason="test")],
        ),
    )
    return Problem.from_scenario(scenario)


def _contexts() -> list[tuple[Problem, OperationalProblem]]:
    contexts = []
    for capacity in (0, 1, 2):
        pb = _problem(capacity)
        hard = build_operational_problem(pb)
        contexts.append((pb, hard))
        contexts.append((pb, override_objective_weights(hard, {"landing_surplus": 0.5})))
    return contexts


@pytest.mark.parametrize("case", range(6))
def test_sanitizer_preview_matches_the_sanitizer(case: int) -> None:
    """Random plans and one- or two-cell edits: preview == sanitize + operator checks."""

    pb, ctx = _contexts()[case]
    sanitizer = ctx.build_sanitizer(Schedule)
    slots = list(ctx.shift_keys)
    machines = [machine.id for machine in pb.scenario.machines]
    choices: list[str | None] = [None, *BLOCKS]
    rng = random.Random(case)
    checked = unchanged_seen = 0
    for _ in range(60):
        plan = {
            machine_id: {slot: rng.choice(choices) for slot in slots} for machine_id in machines
        }
        if rng.random() < 0.5:
            plan = sanitizer(Schedule(plan=plan)).plan  # fixed points as well
        preview = ctx.build_sanitizer_preview(plan)
        for _ in range(25):
            edits = [
                (rng.choice(machines), rng.choice(slots), rng.choice(choices))
                for _ in range(rng.choice((1, 2)))
            ]
            candidate = {machine_id: dict(cells) for machine_id, cells in plan.items()}
            for machine_id, slot, block_id in edits:
                candidate[machine_id][slot] = block_id
            sanitized = sanitizer(Schedule(plan=candidate)).plan
            outcome = preview.outcome(edits)
            assert outcome is not None
            unchanged, values = outcome
            assert unchanged == _plan_equals(sanitized, plan)
            for machine_id, slot, _block_id in edits:
                assert values[(machine_id, slot)] == sanitized[machine_id][slot]
            checked += 1
            unchanged_seen += unchanged
    assert checked == 1500
    assert unchanged_seen > 0


def test_sanitizer_preview_declines_unknown_cells() -> None:
    pb, ctx = _contexts()[0]
    plan = {machine.id: {slot: None for slot in ctx.shift_keys} for machine in pb.scenario.machines}
    preview = ctx.build_sanitizer_preview(plan)
    assert preview.outcome([("ZZ", ctx.shift_keys[0], "B1")]) is None
    assert preview.outcome([("F1", (99, "S1"), "B1")]) is None


def test_fast_shuffle_reproduces_random_shuffle() -> None:
    for seed in range(20):
        for size in (0, 1, 2, 3, 31, 32, 33, 1000, 22155):
            expected = list(range(size))
            actual = list(range(size))
            reference = random.Random(seed)
            fast = random.Random(seed)
            reference.shuffle(expected)
            _shuffle_with_getrandbits(fast, actual)
            assert actual == expected
            assert fast.getstate() == reference.getstate()
    assert registry_module._FAST_SHUFFLE

    class Custom(random.Random):
        pass

    expected = list(range(50))
    actual = list(range(50))
    random.Random(3).shuffle(expected)
    _shuffle(Custom(3), actual)  # subclasses use their own ``shuffle``
    assert actual == expected


def test_operator_tries_do_not_build_full_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """At most one full sanitizer pass and one schedule copy per operator application.

    ``examples/synthetic/small`` (one landing of capacity 1, three shifts a day): a0b2799 needed
    about 400 of each per SA iteration (the cross-exchange operator retried pairs of equal blocks,
    and block insertion moves onto the full landing), 4 since #151.
    """

    calls = {"sanitize": 0, "clone": 0}
    build_sanitizer = OperationalProblem.build_sanitizer

    def counting_build_sanitizer(self, schedule_cls):
        sanitizer = build_sanitizer(self, schedule_cls)

        def counting(schedule):
            calls["sanitize"] += 1
            return sanitizer(schedule)

        return counting

    clone = registry_module._clone_schedule

    def counting_clone(*args, **kwargs):
        calls["clone"] += 1
        return clone(*args, **kwargs)

    monkeypatch.setattr(OperationalProblem, "build_sanitizer", counting_build_sanitizer)
    monkeypatch.setattr(registry_module, "_clone_schedule", counting_clone)
    iterations = 15
    pb = Problem.from_scenario(load_scenario(SYNTHETIC_SMALL))
    result = solve_sa(pb, iters=iterations, seed=42)
    operators = len(result["meta"]["operators"])
    assert result["meta"]["proposals"] > 0
    assert calls["sanitize"] <= operators * iterations
    assert calls["clone"] <= operators * iterations


class ReferenceCrossExchange(CrossExchangeOperator):
    """Cross exchange as in a0b2799: materialised pair list, full sanitizer per try."""

    def apply(self, context):
        schedule = context.schedule
        locks = _locked_assignments(context.problem, context.shift_keys)
        production = _production_rates(context.problem)
        assignments = [
            (machine, shift_key, block_id)
            for machine, machine_plan in schedule.plan.items()
            for shift_key, block_id in machine_plan.items()
            if block_id is not None
        ]
        if len(assignments) < 2:
            return None
        context.rng.shuffle(assignments)
        pairs = list(combinations(assignments, 2))
        context.rng.shuffle(pairs)
        for (machine_a, shift_a, block_a), (machine_b, shift_b, block_b) in pairs:
            if machine_a == machine_b:
                continue
            if (
                locks.get((machine_a, shift_a)) == block_a
                or locks.get((machine_b, shift_b)) == block_b
            ):
                continue
            if production.get((machine_a, block_b), 0.0) <= 0.0:
                continue
            if production.get((machine_b, block_a), 0.0) <= 0.0:
                continue
            if not _window_allows(shift_a[0], block_b, context):
                continue
            if not _window_allows(shift_b[0], block_a, context):
                continue
            candidate = _clone_schedule(context, {machine_a, machine_b})
            _set_slot(context, candidate, machine_a, shift_a, block_b)
            _set_slot(context, candidate, machine_b, shift_b, block_a)
            candidate = context.sanitizer(candidate)
            if _plan_equals(candidate.plan, schedule.plan):
                continue
            if candidate.plan.get(machine_a, {}).get(shift_a) != block_b:
                continue
            if candidate.plan.get(machine_b, {}).get(shift_b) != block_a:
                continue
            return candidate
        return None


def _operator_context(pb, ctx, plan, seed, *, preview: bool) -> OperatorContext:
    return OperatorContext(
        problem=pb,
        schedule=Schedule(plan=plan),
        sanitizer=ctx.build_sanitizer(Schedule),
        rng=random.Random(seed),
        shift_keys=ctx.shift_keys,
        shift_index=ctx.shift_index,
        distance_lookup=ctx.distance_lookup,
        block_windows=ctx.bundle.windows,
        landing_capacity=ctx.bundle.landing_capacity,
        landing_of=ctx.bundle.landing_for_block,
        sanitizer_preview=ctx.build_sanitizer_preview(plan) if preview else None,
    )


@pytest.mark.parametrize("case", range(6))
def test_operators_return_what_they_returned_before_151(
    case: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preview, fast shuffle and pair positions change no operator result or random draw."""

    pb, ctx = _contexts()[case]
    sanitizer = ctx.build_sanitizer(Schedule)
    slots = list(ctx.shift_keys)
    machines = [machine.id for machine in pb.scenario.machines]
    choices: list[str | None] = [None, None, *BLOCKS]
    plan_rng = random.Random(100 + case)
    operators = [
        (BlockInsertionOperator(), BlockInsertionOperator()),
        (CoverageInjectionOperator(), CoverageInjectionOperator()),
        (CrossExchangeOperator(), ReferenceCrossExchange()),
        (MobilisationShakeOperator(), MobilisationShakeOperator()),
    ]
    produced = dict.fromkeys((operator.name for operator, _reference in operators), 0)
    for trial in range(40):
        plan = {
            machine_id: {slot: plan_rng.choice(choices) for slot in slots}
            for machine_id in machines
        }
        if trial % 2:
            plan = sanitizer(Schedule(plan=plan)).plan
        for operator, reference in operators:
            fast = _operator_context(pb, ctx, plan, trial, preview=True)
            result = operator.apply(fast)
            monkeypatch.setattr(registry_module, "_FAST_SHUFFLE", False)
            slow = _operator_context(pb, ctx, plan, trial, preview=False)
            expected = reference.apply(slow)
            monkeypatch.setattr(registry_module, "_FAST_SHUFFLE", True)
            assert (result is None) == (expected is None), operator.name
            if result is not None:
                assert result.plan == expected.plan, operator.name
                produced[operator.name] += 1
            assert fast.rng.getstate() == slow.rng.getstate(), operator.name
    assert all(produced.values()), produced
