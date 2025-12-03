from __future__ import annotations

import random

from fhops.optimization.heuristics.common import Schedule, generate_neighbors
from fhops.optimization.heuristics.registry import (
    BlockInsertionOperator,
    CrossExchangeOperator,
    MobilisationShakeOperator,
    OperatorRegistry,
)
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
from fhops.scheduling.systems import HarvestSystem, SystemJob


def _build_problem(
    *,
    blocks: list[Block],
    machines: list[Machine],
    landings: list[Landing],
    calendar: list[CalendarEntry],
    shift_calendar: list[ShiftCalendarEntry],
    production_rates: list[ProductionRate],
    locked: list[ScheduleLock] | None = None,
    harvest_systems: dict[str, HarvestSystem] | None = None,
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
        harvest_systems=harvest_systems or {},
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
    return generate_neighbors(pb, schedule, registry, rng, {}, ctx)


class ForceLoaderOperator:
    """Test operator that forces loader work on the earliest shift."""

    name = "force_loader"
    weight = 1.0

    def apply(self, context):
        plan = {
            machine: assignments.copy() for machine, assignments in context.schedule.plan.items()
        }
        loader_plan = plan.get("L1")
        if not loader_plan:
            return None
        earliest_key = sorted(loader_plan.keys())[0]
        loader_plan[earliest_key] = "B1"
        schedule_cls = context.schedule.__class__
        candidate = schedule_cls(plan=plan)
        return context.sanitizer(candidate)


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


def test_generate_neighbors_defers_downstream_roles():
    system = HarvestSystem(
        system_id="ground_seq",
        jobs=[
            SystemJob("fell", "feller_buncher", []),
            SystemJob("process", "roadside_processor", ["fell"]),
            SystemJob("load", "loader", ["process"]),
        ],
        role_headstart_shifts={"roadside_processor": 1.0, "loader": 1.0},
    )
    blocks = [
        Block(
            id="B1",
            landing_id="L1",
            work_required=60.0,
            earliest_start=1,
            latest_finish=3,
            harvest_system_id="ground_seq",
        )
    ]
    machines = [
        Machine(id="F1", role="feller_buncher"),
        Machine(id="P1", role="roadside_processor"),
        Machine(id="L1", role="loader"),
    ]
    landings = [Landing(id="L1", daily_capacity=3)]
    calendar = [
        CalendarEntry(machine_id=machine.id, day=day, available=True)
        for machine in machines
        for day in (1, 2, 3)
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id=machine.id, day=day, shift_id="AM", available=True)
        for machine in machines
        for day in (1, 2, 3)
    ]
    production_rates = [
        ProductionRate(machine_id="F1", block_id="B1", rate=20.0),
        ProductionRate(machine_id="P1", block_id="B1", rate=20.0),
        ProductionRate(machine_id="L1", block_id="B1", rate=20.0),
    ]
    pb = _build_problem(
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production_rates,
        harvest_systems={"ground_seq": system},
    )
    schedule = _build_schedule(
        pb,
        {
            ("F1", 1, "AM"): "B1",
            ("P1", 2, "AM"): "B1",
            ("L1", 3, "AM"): "B1",
        },
    )

    neighbors = _run_operator(pb, schedule, ForceLoaderOperator())
    assert neighbors
    repaired = neighbors[0]
    loader_assignments = [day for (day, _), block in repaired.plan["L1"].items() if block == "B1"]
    if loader_assignments:
        assert min(loader_assignments) >= 3
    else:
        assert repaired.plan["L1"][(1, "AM")] is None
