from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from fhops.cli._utils import resolve_operator_presets
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
from fhops.scenario.io.loaders import load_scenario


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


def test_solve_sa_writes_telemetry(tmp_path: Path):
    scenario_path = Path("examples/tiny7/scenario.yaml")
    scenario = load_scenario(scenario_path)
    pb = Problem.from_scenario(scenario)
    log_path = tmp_path / "runs.jsonl"
    res = solve_sa(
        pb,
        iters=10,
        seed=5,
        telemetry_log=log_path,
        telemetry_context={"scenario_path": str(scenario_path)},
    )
    assert log_path.exists()
    assert "kpi_totals" in res["meta"]
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["solver"] == "sa"
    assert record["status"] == "ok"
    assert pytest.approx(record["metrics"]["objective"], rel=1e-6) == res["objective"]
    assert record["run_id"] == res["meta"]["telemetry_run_id"]
    sqlite_path = log_path.with_suffix(".sqlite")
    assert sqlite_path.exists()
    with sqlite3.connect(sqlite_path) as conn:
        rows = conn.execute(
            "SELECT name FROM run_kpis WHERE run_id = ?", (record["run_id"],)
        ).fetchall()
        assert rows
    steps_path = res["meta"].get("telemetry_steps_path")
    assert steps_path
    steps_path = Path(steps_path)
    assert steps_path.exists()
    step_lines = steps_path.read_text(encoding="utf-8").strip().splitlines()
    assert step_lines
    last_step = json.loads(step_lines[-1])
    assert last_step["record_type"] == "step"
    assert last_step["run_id"] == record["run_id"]


def test_solve_sa_invalid_cooling_rate():
    pb = _simple_problem()
    with pytest.raises(ValueError):
        solve_sa(pb, iters=50, seed=1, cooling_rate=1.5)


def test_solve_sa_restart_interval_meta():
    pb = _simple_problem()
    res = solve_sa(pb, iters=50, seed=2, restart_interval=250)
    meta = res["meta"]
    assert meta["restart_interval"] == 250
    assert meta["cooling_rate"] == pytest.approx(0.999)


def test_solve_sa_reports_milp_gap():
    pb = _simple_problem()
    res = solve_sa(pb, iters=5, seed=3, milp_objective=100.0)
    meta = res["meta"]
    assert meta["milp_objective"] == pytest.approx(100.0)
    assert "milp_gap" in meta


def test_sa_preset_applies_objective_weights():
    fixture_path = Path("tests/fixtures/presets/tiny7_explore.yaml")
    config = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    scenario_path = Path(config["scenario"])
    scenario = load_scenario(scenario_path)
    problem = Problem.from_scenario(scenario)
    operators, operator_weights = resolve_operator_presets(config["presets"])
    result = solve_sa(
        problem,
        iters=5,
        seed=13,
        operators=operators,
        operator_weights=operator_weights,
    )
    meta_weights = result["meta"].get("objective_weights")
    assert meta_weights, "solver meta should include objective weight snapshot"
    for key, expected in config["expected_objective_weights"].items():
        assert pytest.approx(meta_weights[key], rel=1e-9) == expected


def test_sa_auto_batch_defaults_for_tiny7():
    scenario = load_scenario(Path("examples/tiny7/scenario.yaml"))
    pb = Problem.from_scenario(scenario)
    res = solve_sa(pb, iters=5, seed=21)
    meta = res["meta"]
    assert meta["batch_size"] == 4
    assert meta["auto_batch_applied"] is True


def test_sa_respects_explicit_batch_size():
    scenario = load_scenario(Path("examples/tiny7/scenario.yaml"))
    pb = Problem.from_scenario(scenario)
    res = solve_sa(pb, iters=5, seed=33, batch_size=2, max_workers=1)
    meta = res["meta"]
    assert meta["batch_size"] == 2
    assert meta["max_workers"] == 1
