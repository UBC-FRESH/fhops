"""Operational MILP landing capacity per shift slot, hard at zero weight (#125).

The heuristics count the machines working a landing's blocks in each ``(day, shift)`` slot and
charge 1000 per machine beyond ``Landing.daily_capacity`` when ``landing_surplus`` is weighted 0,
otherwise ``ω_land`` times the surplus, where the ``k``-th machine beyond capacity adds ``k``. The
MILP (E11) now uses the same rule: per slot, hard at weight 0, ``k·ω_land`` unit slack pieces
otherwise. Before 1.0.1 it limited machine-shifts per *day* with a slack that was free at weight 0.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import pyomo.environ as pyo
import pytest

from fhops.model.milp import driver
from fhops.model.milp.driver import solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.heuristics.common import evaluate_schedule
from fhops.optimization.heuristics.ils import _assignments_to_schedule
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
    ScheduleLock,
)
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scheduling.timeline.models import ShiftDefinition, TimelineConfig

SHIFTS = ("S1", "S2", "S3")
MACHINES = ("M1", "M2", "M3", "M4")


def _scenario(
    *,
    shifts: tuple[str, ...] | None = SHIFTS,
    capacity: int = 1,
    landing_surplus: float = 0.0,
    num_days: int = 2,
    locks: list[ScheduleLock] | None = None,
) -> Scenario:
    timeline = (
        TimelineConfig(
            shifts=[ShiftDefinition(name=s, hours=8.0, shifts_per_day=1) for s in shifts]
        )
        if shifts
        else None
    )
    return Scenario(
        name="landing-slots",
        num_days=num_days,
        # Unsequenced blocks: every machine's output counts, so only landings limit the plan.
        blocks=[
            Block(id="B1", landing_id="L1", work_required=10_000.0),
            Block(id="B2", landing_id="L1", work_required=10_000.0),
        ],
        machines=[Machine(id=m) for m in MACHINES],
        landings=[Landing(id="L1", daily_capacity=capacity)],
        calendar=[
            CalendarEntry(machine_id=m, day=d, available=1)
            for m in MACHINES
            for d in range(1, num_days + 1)
        ],
        production_rates=[
            ProductionRate(machine_id=m, block_id=b, rate=10.0 + i)
            for i, m in enumerate(MACHINES)
            for b in ("B1", "B2")
        ],
        timeline=timeline,
        objective_weights=ObjectiveWeights(
            production=1.0, mobilisation=0.0, landing_surplus=landing_surplus
        ),
        locked_assignments=locks,
    )


def _solve(scenario: Scenario):
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    result = solve_operational_milp(ctx.bundle, solver="highs", context=ctx)
    assert result["outcome"] == "optimal"
    frame = result["assignments"]
    return pb, ctx, result, frame[frame["assigned"] > 0.5]


def _per_slot(frame: pd.DataFrame) -> Counter:
    return Counter((int(r.day), str(r.shift_id)) for r in frame.itertuples(index=False))


def test_hard_capacity_is_per_shift_slot() -> None:
    pb, ctx, result, frame = _solve(_scenario(capacity=2))
    counts = _per_slot(frame)
    # Two machines per slot in every shift of both days (per-day counting allowed only 2 per day
    # plus a free slack); the two fastest machines work.
    assert counts == Counter({(d, s): 2 for d in (1, 2) for s in SHIFTS})
    assert set(frame.machine_id) == {"M3", "M4"}
    assert result["objective"] == pytest.approx(6 * (12.0 + 13.0) - 20_000 + 6 * 25.0, abs=1e-6)
    model = build_operational_model(ctx.bundle)
    assert not hasattr(model, "landing_surplus")
    assert len(model.landing_capacity) == 2 * len(SHIFTS)

    # The heuristics' evaluation of the MILP plan charges no landing penalty.
    debug: dict[str, object] = {}
    evaluate_schedule(pb, _assignments_to_schedule(pb, frame), ctx, debug=debug)
    assert debug["penalty_total"] == 0.0
    assert debug["landing_surplus_total"] == 0.0


def test_single_shift_slot_equals_day() -> None:
    _, ctx, _, frame = _solve(_scenario(shifts=None, capacity=3))
    assert _per_slot(frame) == Counter({(1, "S1"): 3, (2, "S1"): 3})
    model = build_operational_model(ctx.bundle)
    assert sorted(model.landing_capacity.keys()) == [("L1", 1, "S1"), ("L1", 2, "S1")]


def _all_locked(day: int = 1, shift: str = "S1") -> list[ScheduleLock]:
    return [ScheduleLock(machine_id=m, block_id="B1", day=day, shift_id=shift) for m in MACHINES]


def test_soft_capacity_prices_kth_surplus_machine_like_the_heuristics() -> None:
    # Four machines locked on a capacity-1 landing: surplus 3 → 1 + 2 + 3 = 6 (heuristics).
    weight = 0.5
    scenario = _scenario(landing_surplus=weight, num_days=1, shifts=("S1",), locks=_all_locked())
    pb, ctx, result, frame = _solve(scenario)
    assert len(frame) == 4
    debug: dict[str, object] = {}
    evaluate_schedule(pb, _assignments_to_schedule(pb, frame), ctx, debug=debug)
    assert debug["landing_surplus_total"] == pytest.approx(6.0)
    # MILP objective = production − leftovers − ω·6, the heuristic objective of the same plan.
    produced = 10.0 + 11.0 + 12.0 + 13.0
    expected = produced - (20_000.0 - produced) - weight * 6.0
    assert result["objective"] == pytest.approx(expected, abs=1e-6)


def test_soft_capacity_allows_priced_overload() -> None:
    # A surplus weight below the production gain of an extra machine keeps it working.
    _, _, _, frame = _solve(_scenario(landing_surplus=0.5, capacity=1, num_days=1))
    assert max(_per_slot(frame).values()) > 1


def test_locks_exceeding_hard_capacity_stay_feasible() -> None:
    scenario = _scenario(capacity=2, locks=_all_locked(day=1, shift="S2"))
    _, _, result, frame = _solve(scenario)
    counts = _per_slot(frame)
    assert counts[(1, "S2")] == 4  # the locks
    assert all(n <= 2 for slot, n in counts.items() if slot != (1, "S2"))
    assert any("exceed its capacity 2" in w for w in result["warnings"])


def test_warm_start_seeds_slot_surplus_pieces() -> None:
    scenario = _scenario(landing_surplus=0.5, num_days=1, shifts=("S1",))
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    incumbent = pd.DataFrame(
        [dict(machine_id=m, block_id="B1", day=1, shift_id="S1", assigned=1) for m in MACHINES[:3]]
    )
    model = build_operational_model(ctx.bundle)
    model._warm_start_meta["operational_problem"] = ctx
    assert driver._apply_incumbent_start(model, incumbent) > 0
    seeded = {k[3]: pyo.value(var) for k, var in model.landing_surplus.items()}
    assert seeded == {1: 1.0, 2: 1.0, 3: 0.0}  # 3 machines on a capacity-1 landing
    assert driver._max_violation(model) <= 1e-6

    result = solve_operational_milp(
        ctx.bundle, solver="highs", context=ctx, incumbent_assignments=incumbent
    )
    assert result["outcome"] == "optimal"
    assert result["warm_start"]["accepted"] is True
