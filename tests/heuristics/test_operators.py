from __future__ import annotations

import random

from fhops.optimization.heuristics.registry import (
    BlockInsertionOperator,
    CrossExchangeOperator,
    MobilisationShakeOperator,
    OperatorRegistry,
)
from fhops.optimization.heuristics.sa import Schedule, _neighbors
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
from fhops.scenario.contract.models import ScheduleLock, ShiftCalendarEntry


def _build_problem(
    *,
    blocks: list[Block],
    machines: list[Machine],
    landings: list[Landing],
    calendar: list[CalendarEntry],
    shift_calendar: list[ShiftCalendarEntry],
    production_rates: list[ProductionRate],
    locked: list[ScheduleLock] | None = None,
) -> Problem:
    scenario = Scenario(
        name="unit-test",
        num_days=max(entry.day for entry in calendar),
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production_rates,
        locked_assignments=locked or [],
    )
    return Problem.from_scenario(scenario)


def _build_schedule(pb: Problem, assignments: dict[tuple[str, int, str], str | None]) -> Schedule:
    plan: dict[str, dict[tuple[int, str], str | None]] = {}
    for machine in pb.scenario.machines:
        plan[machine.id] = {(shift.day, shift.shift_id): None for shift in pb.shifts}
    for (machine_id, day, shift_id), block_id in assignments.items():
        plan[machine_id][(day, shift_id)] = block_id
    return Schedule(plan=plan)


def _run_operator(
    pb: Problem,
    schedule: Schedule,
    operator,
    rng_seed: int = 0,
) -> list[Schedule]:
    registry = OperatorRegistry.from_defaults([operator])
    rng = random.Random(rng_seed)
    ctx = build_operational_problem(pb)
    return _neighbors(pb, schedule, registry, rng, {}, ctx)


def test_block_insertion_respects_windows_and_availability():
    blocks = [
        Block(
            id="B1",
            landing_id="L1",
            work_required=10.0,
            earliest_start=1,
            latest_finish=1,
        )
    ]
    machines = [Machine(id="M1", role="harvester"), Machine(id="M2", role="harvester")]
    landings = [Landing(id="L1", daily_capacity=10)]
    calendar = [
        CalendarEntry(machine_id="M1", day=1, available=True),
        CalendarEntry(machine_id="M1", day=2, available=True),
        CalendarEntry(machine_id="M2", day=1, available=False),
        CalendarEntry(machine_id="M2", day=2, available=True),
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id="M1", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M1", day=2, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=1, shift_id="AM", available=False),
        ShiftCalendarEntry(machine_id="M2", day=2, shift_id="AM", available=True),
    ]
    production = [
        ProductionRate(machine_id="M1", block_id="B1", rate=10.0),
        ProductionRate(machine_id="M2", block_id="B1", rate=10.0),
    ]
    pb = _build_problem(
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production,
    )
    schedule = _build_schedule(pb, {("M1", 1, "AM"): "B1"})

    neighbors = _run_operator(pb, schedule, BlockInsertionOperator(weight=1.0))
    assert neighbors == []  # no feasible target slots within the window


def test_block_insertion_moves_within_window():
    blocks = [
        Block(
            id="B1",
            landing_id="L1",
            work_required=10.0,
            earliest_start=1,
            latest_finish=2,
        )
    ]
    machines = [Machine(id="M1", role="harvester"), Machine(id="M2", role="harvester")]
    landings = [Landing(id="L1", daily_capacity=10)]
    calendar = [
        CalendarEntry(machine_id="M1", day=1, available=True),
        CalendarEntry(machine_id="M1", day=2, available=True),
        CalendarEntry(machine_id="M2", day=1, available=False),
        CalendarEntry(machine_id="M2", day=2, available=True),
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id="M1", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M1", day=2, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=1, shift_id="AM", available=False),
        ShiftCalendarEntry(machine_id="M2", day=2, shift_id="AM", available=True),
    ]
    production = [
        ProductionRate(machine_id="M1", block_id="B1", rate=10.0),
        ProductionRate(machine_id="M2", block_id="B1", rate=10.0),
    ]
    pb = _build_problem(
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production,
    )
    schedule = _build_schedule(pb, {("M1", 1, "AM"): "B1"})

    neighbors = _run_operator(pb, schedule, BlockInsertionOperator(weight=1.0))
    assert len(neighbors) == 1
    moved = neighbors[0]
    assert moved.plan["M1"][(1, "AM")] is None
    assert moved.plan["M1"][(2, "AM")] == "B1"


def test_cross_exchange_requires_capable_machines():
    blocks = [
        Block(id="B1", landing_id="L1", work_required=10.0, earliest_start=1, latest_finish=1),
        Block(id="B2", landing_id="L1", work_required=10.0, earliest_start=1, latest_finish=1),
    ]
    machines = [Machine(id="M1", role="harvester"), Machine(id="M2", role="harvester")]
    landings = [Landing(id="L1", daily_capacity=10)]
    calendar = [
        CalendarEntry(machine_id="M1", day=1, available=True),
        CalendarEntry(machine_id="M2", day=1, available=True),
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id="M1", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=1, shift_id="AM", available=True),
    ]
    production = [
        ProductionRate(machine_id="M1", block_id="B1", rate=10.0),
        ProductionRate(machine_id="M2", block_id="B2", rate=10.0),
    ]
    pb = _build_problem(
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production,
    )
    schedule = _build_schedule(
        pb,
        {
            ("M1", 1, "AM"): "B1",
            ("M2", 1, "AM"): "B2",
        },
    )

    neighbors = _run_operator(pb, schedule, CrossExchangeOperator(weight=1.0))
    assert neighbors == []  # machines cannot execute the opposite blocks


def test_cross_exchange_swaps_when_valid():
    blocks = [
        Block(id="B1", landing_id="L1", work_required=10.0, earliest_start=1, latest_finish=1),
        Block(id="B2", landing_id="L1", work_required=10.0, earliest_start=1, latest_finish=1),
    ]
    machines = [Machine(id="M1", role="harvester"), Machine(id="M2", role="harvester")]
    landings = [Landing(id="L1", daily_capacity=10)]
    calendar = [
        CalendarEntry(machine_id="M1", day=1, available=True),
        CalendarEntry(machine_id="M2", day=1, available=True),
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id="M1", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=1, shift_id="AM", available=True),
    ]
    production = [
        ProductionRate(machine_id="M1", block_id="B1", rate=10.0),
        ProductionRate(machine_id="M2", block_id="B2", rate=10.0),
        ProductionRate(machine_id="M1", block_id="B2", rate=10.0),
        ProductionRate(machine_id="M2", block_id="B1", rate=10.0),
    ]
    pb = _build_problem(
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production,
    )
    schedule = _build_schedule(
        pb,
        {
            ("M1", 1, "AM"): "B1",
            ("M2", 1, "AM"): "B2",
        },
    )

    neighbors = _run_operator(pb, schedule, CrossExchangeOperator(weight=1.0), rng_seed=1)
    assert neighbors, "expected a feasible cross exchange"
    swapped = neighbors[0]
    assert swapped.plan["M1"][(1, "AM")] == "B2"
    assert swapped.plan["M2"][(1, "AM")] == "B1"


def test_mobilisation_shake_respects_minimum_spacing_and_locks():
    blocks = [
        Block(id="B1", landing_id="L1", work_required=10.0, earliest_start=1, latest_finish=1),
    ]
    machines = [Machine(id="M1", role="harvester")]
    landings = [Landing(id="L1", daily_capacity=10)]
    calendar = [
        CalendarEntry(machine_id="M1", day=1, available=True),
        CalendarEntry(machine_id="M1", day=2, available=True),
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id="M1", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M1", day=2, shift_id="AM", available=True),
    ]
    production = [ProductionRate(machine_id="M1", block_id="B1", rate=10.0)]
    lock = [ScheduleLock(machine_id="M1", day=1, block_id="B1")]
    pb = _build_problem(
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production,
        locked=lock,
    )
    schedule = _build_schedule(pb, {("M1", 1, "AM"): "B1"})

    neighbors = _run_operator(pb, schedule, MobilisationShakeOperator(weight=1.0, min_day_delta=1))
    assert neighbors == []  # lock prevents moves


def test_mobilisation_shake_moves_when_window_allows_distance():
    blocks = [
        Block(id="B1", landing_id="L1", work_required=10.0, earliest_start=1, latest_finish=3),
    ]
    machines = [Machine(id="M1", role="harvester")]
    landings = [Landing(id="L1", daily_capacity=10)]
    calendar = [
        CalendarEntry(machine_id="M1", day=1, available=True),
        CalendarEntry(machine_id="M1", day=2, available=True),
        CalendarEntry(machine_id="M1", day=3, available=True),
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id="M1", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M1", day=2, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M1", day=3, shift_id="AM", available=True),
    ]
    production = [ProductionRate(machine_id="M1", block_id="B1", rate=10.0)]
    pb = _build_problem(
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production,
    )
    schedule = _build_schedule(pb, {("M1", 1, "AM"): "B1"})

    neighbors = _run_operator(pb, schedule, MobilisationShakeOperator(weight=1.0, min_day_delta=1))
    assert neighbors, "expected mobilisation shake to relocate within the allowed window"
    candidate = neighbors[0]
    assert candidate.plan["M1"][(1, "AM")] is None
    assert candidate.plan["M1"][(3, "AM")] == "B1"
