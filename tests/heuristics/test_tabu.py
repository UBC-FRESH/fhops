from __future__ import annotations

from fhops.optimization.heuristics import solve_tabu
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


def _problem() -> Problem:
    blocks = [
        Block(id="B1", landing_id="L1", work_required=4.0, earliest_start=1, latest_finish=2),
        Block(id="B2", landing_id="L1", work_required=4.0, earliest_start=1, latest_finish=2),
    ]
    machines = [
        Machine(id="M1", role="harvester"),
        Machine(id="M2", role="harvester"),
    ]
    landings = [Landing(id="L1", daily_capacity=2)]
    calendar = [
        CalendarEntry(machine_id="M1", day=1, available=True),
        CalendarEntry(machine_id="M1", day=2, available=True),
        CalendarEntry(machine_id="M2", day=1, available=True),
        CalendarEntry(machine_id="M2", day=2, available=True),
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id="M1", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M1", day=2, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=1, shift_id="AM", available=True),
        ShiftCalendarEntry(machine_id="M2", day=2, shift_id="AM", available=True),
    ]
    production = [
        ProductionRate(machine_id="M1", block_id="B1", rate=4.0),
        ProductionRate(machine_id="M1", block_id="B2", rate=4.0),
        ProductionRate(machine_id="M2", block_id="B1", rate=4.0),
        ProductionRate(machine_id="M2", block_id="B2", rate=4.0),
    ]
    scenario = Scenario(
        name="tabu",
        num_days=2,
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production,
    )
    return Problem.from_scenario(scenario)


def test_solve_tabu_basic():
    pb = _problem()
    result = solve_tabu(pb, iters=200, seed=5, stall_limit=50)
    assert "objective" in result
    assert result["objective"] >= 0
    assert not result["assignments"].empty


def test_solve_tabu_respects_operators():
    pb = _problem()
    result = solve_tabu(pb, iters=100, seed=1, operators=["swap"], stall_limit=30)
    assert "operators" in result["meta"]
    weights = result["meta"]["operators"]
    assert weights.get("swap", 0.0) > 0
    assert weights.get("move", 0.0) >= 0
    assert weights.get("block_insertion", 0.0) == 0.0


def test_solve_tabu_records_restarts_when_stalled():
    pb = _problem()
    result = solve_tabu(pb, iters=200, seed=3, stall_limit=1)
    meta = result["meta"]
    assert meta.get("restarts", 0) >= 1
    assert meta.get("iterations") == 200
