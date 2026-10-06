"""The operational MILP honours ``Scenario.timeline`` blackouts like the heuristics (#110)."""

from __future__ import annotations

import pytest

from fhops.model.milp.data import (
    build_blackout_slots,
    build_operational_bundle,
    bundle_from_dict,
    bundle_to_dict,
)
from fhops.model.milp.driver import solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.heuristics import solve_sa
from fhops.optimization.operational_problem import build_operational_problem
from fhops.planning import solve_rolling_plan
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)
from fhops.scenario.contract.models import ShiftCalendarEntry
from fhops.scheduling.timeline.models import BlackoutWindow, ShiftDefinition, TimelineConfig


def _scenario(
    *,
    num_days: int = 4,
    shifts: tuple[str, ...] = ("S1", "S2"),
    blackouts: list[BlackoutWindow] | None = None,
    shift_calendar: list[ShiftCalendarEntry] | None = None,
) -> Scenario:
    machines = [Machine(id="M1"), Machine(id="M2")]
    return Scenario(
        name="blackouts",
        num_days=num_days,
        blocks=[Block(id="B1", landing_id="L1", work_required=1000.0)],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=10)],
        calendar=[
            CalendarEntry(machine_id=m.id, day=d, available=1)
            for m in machines
            for d in range(1, num_days + 1)
        ],
        shift_calendar=shift_calendar,
        production_rates=[
            ProductionRate(machine_id=m.id, block_id="B1", rate=40.0) for m in machines
        ],
        timeline=TimelineConfig(
            shifts=[ShiftDefinition(name=s, hours=8.0, shifts_per_day=1) for s in shifts],
            blackouts=blackouts or [],
        ),
    )


def _worked_slots(assignments) -> set[tuple[str, int, str]]:
    rows = assignments[assignments["assigned"] > 0]
    return {(r.machine_id, int(r.day), str(r.shift_id)) for r in rows.itertuples()}


def test_blackout_slots_match_heuristic_context() -> None:
    scenario = _scenario(blackouts=[BlackoutWindow(start_day=2, end_day=3, reason="fire")])
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    expected = {(m, d, s) for m in ("M1", "M2") for d in (2, 3) for s in ("S1", "S2")}
    assert set(build_blackout_slots(pb)) == expected
    assert ctx.blackout_shifts == frozenset(expected)
    assert set(ctx.bundle.blackout_slots) == expected
    assert bundle_from_dict(bundle_to_dict(ctx.bundle)).blackout_slots == ctx.bundle.blackout_slots


def test_blackout_slots_follow_machine_shift_calendar() -> None:
    shift_calendar = [
        ShiftCalendarEntry(machine_id=m, day=d, shift_id=s, available=1)
        for m in ("M1", "M2")
        for d in (1, 2)
        for s in (("N",) if m == "M2" and d == 2 else ("S1", "S2"))
    ]
    scenario = _scenario(
        num_days=2,
        shift_calendar=shift_calendar,
        blackouts=[BlackoutWindow(start_day=2, end_day=2)],
    )
    slots = set(build_blackout_slots(Problem.from_scenario(scenario)))
    assert slots == {("M1", 2, "S1"), ("M1", 2, "S2"), ("M2", 2, "N")}


def test_no_blackouts_leave_bundle_unchanged() -> None:
    bundle = build_operational_bundle(Problem.from_scenario(_scenario()))
    assert bundle.blackout_slots == ()
    assert "blackout_slots" not in bundle_to_dict(bundle)


def test_milp_zero_availability_in_blackout_slots() -> None:
    scenario = _scenario(blackouts=[BlackoutWindow(start_day=2, end_day=3)])
    bundle = build_operational_bundle(Problem.from_scenario(scenario))
    model = build_operational_model(bundle)
    assert model.machine_capacity["M1", 2, "S1"].upper == 0.0
    assert model.machine_capacity["M1", 2, "S1"].lower == 0.0
    assert model.machine_capacity["M1", 1, "S1"].upper == 1.0


def test_milp_and_heuristic_agree_on_blackouts() -> None:
    scenario = _scenario(blackouts=[BlackoutWindow(start_day=2, end_day=3, reason="fire")])
    pb = Problem.from_scenario(scenario)
    blocked = set(build_operational_problem(pb).blackout_shifts)

    milp = solve_operational_milp(build_operational_bundle(pb), solver="highs", time_limit=30)
    assert milp["termination_condition"].lower() == "optimal"
    milp_slots = _worked_slots(milp["assignments"])
    sa_slots = _worked_slots(solve_sa(pb, iters=200, seed=3)["assignments"])

    open_slots = {(m, d, s) for m in ("M1", "M2") for d in (1, 4) for s in ("S1", "S2")}
    assert not milp_slots & blocked
    assert not sa_slots & blocked
    # Both solver families use every open slot (the block cannot be finished in the horizon).
    assert milp_slots == open_slots
    assert sa_slots == open_slots
    assert milp["production"] == pytest.approx(8 * 40.0)


def test_rolling_milp_honours_rebased_blackouts() -> None:
    scenario = _scenario(num_days=6, blackouts=[BlackoutWindow(start_day=4, end_day=4)])
    result = solve_rolling_plan(
        scenario, master_days=6, subproblem_days=3, lock_days=2, solver="mip", mip_time_limit=30
    )
    assert result.locked_assignments
    assert not [lock for lock in result.locked_assignments if lock.day == 4]
    assert {lock.day for lock in result.locked_assignments} == {1, 2, 3, 5, 6}
