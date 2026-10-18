"""Multi-shift heuristic repair respects landing capacity (#116).

Since #109 the repair releases staged output to downstream roles at the next *shift* (formulation
E7). On multi-shift days that let the repair stack every role of a block on its landing in the
same shift, so greedy seeds and SA plans on the Jaffray three-shift scenarios paid more 1000-point
landing-capacity penalties than FHOPS 1.0.0. On multi-shift days the repair now keeps/fills an
assignment only when the block's landing has room in that shift (hard landing penalties only).
Since #140 the guard applies on every day (single-shift days included) and a capacity-0 landing
admits no machine.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import pytest

from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics import solve_sa
from fhops.optimization.heuristics.common import evaluate_schedule, init_greedy_schedule
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scheduling.systems import HarvestSystem, SystemJob
from fhops.scheduling.timeline.models import ShiftDefinition, TimelineConfig

FLEET = {
    "FB1": ("feller_buncher", 60.0),
    "FB2": ("feller_buncher", 40.0),
    "SK1": ("grapple_skidder", 50.0),
    "SK2": ("grapple_skidder", 45.0),
    "PR1": ("processor", 70.0),
    "LD1": ("loader", 90.0),
}


def _scenario(
    *,
    shifts: tuple[str, ...] | None = ("S1", "S2", "S3"),
    num_days: int = 6,
    landing_capacity: int = 2,
    landing_surplus: float | None = None,
) -> Scenario:
    system = HarvestSystem(
        system_id="pipe",
        jobs=[
            SystemJob("felling", "feller_buncher", []),
            SystemJob("primary_transport", "grapple_skidder", ["felling"]),
            SystemJob("processing", "processor", ["primary_transport"]),
            SystemJob("loading", "loader", ["processing"]),
        ],
    )
    blocks = {"B1": ("L1", 400.0), "B2": ("L2", 300.0), "B3": ("L3", 350.0)}
    timeline = (
        TimelineConfig(
            shifts=[ShiftDefinition(name=s, hours=8.0, shifts_per_day=1) for s in shifts]
        )
        if shifts
        else None
    )
    weights = (
        ObjectiveWeights(production=1.0, mobilisation=0.5, landing_surplus=landing_surplus)
        if landing_surplus is not None
        else None
    )
    return Scenario(
        name="multishift-landing",
        num_days=num_days,
        blocks=[
            Block(id=bid, landing_id=lid, work_required=work, harvest_system_id="pipe")
            for bid, (lid, work) in blocks.items()
        ],
        machines=[Machine(id=mid, role=role) for mid, (role, _rate) in FLEET.items()],
        landings=[Landing(id=lid, daily_capacity=landing_capacity) for lid in ("L1", "L2", "L3")],
        calendar=[
            CalendarEntry(machine_id=mid, day=d, available=1)
            for mid in FLEET
            for d in range(1, num_days + 1)
        ],
        production_rates=[
            ProductionRate(machine_id=mid, block_id=bid, rate=rate)
            for mid, (_role, rate) in FLEET.items()
            for bid in blocks
        ],
        harvest_systems={"pipe": system},
        timeline=timeline,
        objective_weights=weights,
    )


def _landing_excess(pb: Problem, plan_rows: list[tuple[str, str, int, str]]) -> int:
    landing_of = {block.id: block.landing_id for block in pb.scenario.blocks}
    capacity = {landing.id: landing.daily_capacity for landing in pb.scenario.landings}
    used = Counter((day, shift, landing_of[block]) for _m, block, day, shift in plan_rows)
    return sum(max(0, count - capacity[key[2]]) for key, count in used.items())


def _schedule_rows(schedule) -> list[tuple[str, str, int, str]]:
    return [
        (machine, block, day, shift)
        for machine, plan in schedule.plan.items()
        for (day, shift), block in plan.items()
        if block is not None
    ]


def test_multi_shift_days_recorded_on_context() -> None:
    multi = build_operational_problem(Problem.from_scenario(_scenario()))
    single = build_operational_problem(Problem.from_scenario(_scenario(shifts=None)))
    assert multi.multi_shift_days == frozenset(range(1, 7))
    assert single.multi_shift_days == frozenset()


def test_greedy_repair_respects_landing_capacity_on_multi_shift_days() -> None:
    pb = Problem.from_scenario(_scenario())
    ctx = build_operational_problem(pb)
    schedule = init_greedy_schedule(pb, ctx)
    debug: dict[str, object] = {}
    evaluate_schedule(pb, schedule, ctx, debug=debug)
    assert _landing_excess(pb, _schedule_rows(schedule)) == 0
    assert debug["penalty_total"] == 0.0
    assert debug["sequencing_violation_count"] == 0
    assert debug["delivered_total"] > 0.0


def test_landing_guard_inactive_with_soft_landing_surplus() -> None:
    # A positive landing_surplus weight makes overloads a priced choice; the repair keeps them.
    pb = Problem.from_scenario(_scenario(landing_surplus=0.05))
    ctx = build_operational_problem(pb)
    schedule = init_greedy_schedule(pb, ctx)
    debug: dict[str, object] = {}
    evaluate_schedule(pb, schedule, ctx, debug=debug)
    assert _landing_excess(pb, _schedule_rows(schedule)) > 0
    assert debug["landing_surplus_total"] > 0.0


def test_landing_guard_applied_on_single_shift_days() -> None:
    # Since #140 the guard applies on every day: before, single-shift days kept the pre-#116
    # repair and the greedy seed overloaded the landings (all med42 heuristic plans carried
    # 49-61 overloads that the MILP forbids).
    pb = Problem.from_scenario(_scenario(shifts=None, num_days=12))
    ctx = build_operational_problem(pb)
    schedule = init_greedy_schedule(pb, ctx)
    debug: dict[str, object] = {}
    evaluate_schedule(pb, schedule, ctx, debug=debug)
    assert _landing_excess(pb, _schedule_rows(schedule)) == 0
    assert debug["penalty_total"] == 0.0
    assert debug["sequencing_violation_count"] == 0
    assert debug["delivered_total"] > 0.0


@pytest.mark.parametrize("shifts", [None, ("S1", "S2", "S3")])
def test_zero_capacity_landing_admits_no_machine(shifts: tuple[str, ...] | None) -> None:
    # A capacity-0 landing admitted one machine per slot before #140 (the repair's room check
    # only tripped once another machine was counted, and the sanitizer treated 0 as unlimited).
    scenario = _scenario(shifts=shifts)
    landings = [
        Landing(id="L1", daily_capacity=2),
        Landing(id="L2", daily_capacity=0),
        Landing(id="L3", daily_capacity=2),
    ]
    pb = Problem.from_scenario(scenario.model_copy(update={"landings": landings}))
    ctx = build_operational_problem(pb)
    schedule = init_greedy_schedule(pb, ctx)
    debug: dict[str, object] = {}
    score = evaluate_schedule(pb, schedule, ctx, debug=debug)
    assert all(block != "B2" for _m, block, _d, _s in _schedule_rows(schedule))
    assert debug["penalty_total"] == 0.0
    # Search plans keep the landing empty, and their objective is the fresh evaluation.
    result = solve_sa(pb, iters=200, seed=1)
    assert "B2" not in set(result["assignments"]["block_id"])
    assert score <= result["objective"] + 1e-6


def test_sanitizer_drops_zero_capacity_landing_only_when_hard() -> None:
    from fhops.optimization.heuristics.common import Schedule

    landings = [
        Landing(id="L1", daily_capacity=2),
        Landing(id="L2", daily_capacity=0),
        Landing(id="L3", daily_capacity=2),
    ]
    for surplus, expected in ((None, None), (0.05, "B2")):
        scenario = _scenario(shifts=None, landing_surplus=surplus)
        pb = Problem.from_scenario(scenario.model_copy(update={"landings": landings}))
        ctx = build_operational_problem(pb)
        plan = {m: {key: None for key in ctx.shift_keys} for m in FLEET}
        plan["FB1"][ctx.shift_keys[0]] = "B2"
        sanitized = ctx.build_sanitizer(Schedule)(Schedule(plan=plan))
        assert sanitized.plan["FB1"][ctx.shift_keys[0]] == expected


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_sa_multi_shift_plan_has_no_landing_overload_and_replays_clean(seed: int) -> None:
    pb = Problem.from_scenario(_scenario())
    result = solve_sa(pb, iters=300, seed=seed)
    assignments: pd.DataFrame = result["assignments"]
    rows = [
        (row.machine_id, row.block_id, int(row.day), str(row.shift_id))
        for row in assignments.itertuples()
        if row.assigned > 0
    ]
    assert _landing_excess(pb, rows) == 0
    kpis = compute_kpis(pb, assignments)
    assert kpis["sequencing_violation_count"] == 0
    # No penalty term: objective = delivered - leftover (no mobilisation parameters here).
    delivered = float(kpis["total_production"])
    leftover = float(kpis["remaining_work_total"])
    assert result["objective"] == pytest.approx(delivered - leftover, abs=1e-6)
