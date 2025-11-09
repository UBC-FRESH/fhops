from __future__ import annotations

import pytest

from fhops.optimization.heuristics import solve_sa
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


def _simple_problem() -> Problem:
    blocks = [
        Block(id="B1", landing_id="L1", work_required=8.0, earliest_start=1, latest_finish=3),
        Block(id="B2", landing_id="L1", work_required=6.0, earliest_start=1, latest_finish=3),
    ]
    machines = [
        Machine(id="M1", role="harvester"),
        Machine(id="M2", role="harvester"),
    ]
    landings = [Landing(id="L1", daily_capacity=2)]
    calendar = [
        CalendarEntry(machine_id="M1", day=1, available=True),
        CalendarEntry(machine_id="M1", day=2, available=True),
        CalendarEntry(machine_id="M1", day=3, available=True),
        CalendarEntry(machine_id="M2", day=1, available=True),
        CalendarEntry(machine_id="M2", day=2, available=True),
        CalendarEntry(machine_id="M2", day=3, available=True),
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id="M1", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M1", day=2, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M1", day=3, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=2, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=3, shift_id="AM", available=True),
    ]
    production_rates = [
        ProductionRate(machine_id="M1", block_id="B1", rate=4.0),
        ProductionRate(machine_id="M1", block_id="B2", rate=3.0),
        ProductionRate(machine_id="M2", block_id="B1", rate=3.0),
        ProductionRate(machine_id="M2", block_id="B2", rate=4.0),
    ]
    scenario = Scenario(
        name="sa-batch",
        num_days=3,
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production_rates,
    )
    return Problem.from_scenario(scenario)


def test_solve_sa_batch_matches_single():
    pb = _simple_problem()
    base = solve_sa(pb, iters=300, seed=77)
    batched = solve_sa(pb, iters=300, seed=77, batch_size=3, max_workers=2)
    assert pytest.approx(base["objective"], rel=1e-6) == batched["objective"]


def test_evaluate_candidates_empty():
    pb = _simple_problem()
    batched = solve_sa(pb, iters=1, seed=1, batch_size=0, max_workers=4)
    assert "objective" in batched
