from __future__ import annotations

import pandas as pd

from fhops.optimization.heuristics import ils as ils_module
from fhops.optimization.heuristics import solve_ils
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
        name="ils",
        num_days=2,
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production,
    )
    return Problem.from_scenario(scenario)


def test_solve_ils_basic():
    pb = _problem()
    result = solve_ils(pb, iters=50, seed=7, stall_limit=5)
    assert "objective" in result
    assert result["objective"] >= 0
    assert not result["assignments"].empty
    assert result["meta"]["algorithm"] == "ils"


def test_solve_ils_respects_operators():
    pb = _problem()
    result = solve_ils(pb, iters=30, seed=3, operators=["swap"], stall_limit=5)
    weights = result["meta"]["operators"]
    assert weights.get("swap", 0.0) > 0
    assert weights.get("move", 0.0) >= 0
    assert weights.get("block_insertion", 0.0) == 0.0


def test_solve_ils_hybrid_invokes_mip(monkeypatch):
    pb = _problem()
    fres = pd.DataFrame(
        [
            {"machine_id": "M1", "block_id": "B1", "day": 1, "shift_id": "AM", "assigned": 1},
            {"machine_id": "M2", "block_id": "B2", "day": 1, "shift_id": "AM", "assigned": 1},
        ]
    )

    calls: dict[str, int] = {"count": 0}

    def fake_solve_mip(*args, **kwargs):
        calls["count"] += 1
        return {"assignments": fres.copy(), "objective": 50.0}

    monkeypatch.setattr(ils_module, "solve_mip", fake_solve_mip)
    result = solve_ils(
        pb,
        iters=3,
        seed=1,
        stall_limit=1,
        hybrid_use_mip=True,
        hybrid_mip_time_limit=1,
    )
    assert calls["count"] >= 1
    assert result["meta"]["hybrid_used"] is True
    expected = ils_module._evaluate(pb, ils_module._assignments_to_schedule(pb, fres))
    assert result["objective"] == expected
