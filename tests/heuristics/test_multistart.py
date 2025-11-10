from __future__ import annotations

from pathlib import Path

import pytest

from fhops.optimization.heuristics import build_exploration_plan, run_multi_start
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


def _build_problem() -> Problem:
    blocks = [
        Block(id="B1", landing_id="L1", work_required=5.0, earliest_start=1, latest_finish=2),
        Block(id="B2", landing_id="L1", work_required=5.0, earliest_start=1, latest_finish=2),
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
    production_rates = [
        ProductionRate(machine_id="M1", block_id="B1", rate=5.0),
        ProductionRate(machine_id="M2", block_id="B2", rate=5.0),
    ]
    scenario = Scenario(
        name="multistart",
        num_days=2,
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=production_rates,
    )
    return Problem.from_scenario(scenario)


def test_run_multi_start_returns_best_result(tmp_path: Path):
    pb = _build_problem()
    seeds = [101, 202]
    presets = [None, ["explore"]]
    result = run_multi_start(
        pb,
        seeds,
        presets=presets,
        max_workers=1,
        sa_kwargs={"iters": 200},
    )
    assert result.best_result["objective"] is not None
    best_obj = result.best_result["objective"]
    assert len(result.runs_meta) == len(seeds)
    for meta in result.runs_meta:
        if meta.get("status") == "ok":
            assert best_obj >= meta["objective"]


def test_run_multi_start_raises_when_all_fail():
    pb = _build_problem()
    seeds = [1]
    presets = [["does-not-exist"]]
    with pytest.raises(RuntimeError):
        run_multi_start(pb, seeds, presets=presets, max_workers=1, sa_kwargs={"iters": 50})


def test_run_multi_start_writes_telemetry(tmp_path: Path):
    log_path = tmp_path / "runs.jsonl"
    pb = _build_problem()
    result = run_multi_start(
        pb,
        seeds=[10, 20],
        presets=[None, ["explore"]],
        max_workers=1,
        sa_kwargs={"iters": 100},
        telemetry_log=log_path,
    )
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(result.runs_meta) + 1  # includes summary record
    summary = lines[-1]
    assert "multi_start_summary" in summary


def test_build_exploration_plan_defaults():
    seeds, presets = build_exploration_plan(6, base_seed=10)
    assert seeds == [10, 1010, 2010, 3010, 4010, 5010]
    expected = [
        None,
        ["explore"],
        ["mobilisation"],
        ["stabilise"],
        None,
        ["explore"],
    ]
    assert presets == expected


def test_build_exploration_plan_custom_presets():
    seeds, presets = build_exploration_plan(3, base_seed=5, presets=["swap-only", "move-only"])
    assert seeds == [5, 1005, 2005]
    assert presets == [["swap-only"], ["move-only"], ["swap-only"]]
