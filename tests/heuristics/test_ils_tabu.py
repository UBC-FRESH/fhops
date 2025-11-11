from __future__ import annotations

import json
from pathlib import Path

from fhops.optimization.heuristics import solve_ils, solve_tabu
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario


def _load_problem() -> Problem:
    scenario = load_scenario("examples/minitoy/scenario.yaml")
    return Problem.from_scenario(scenario)


def _read_first_record(path: Path) -> dict[str, object]:
    line = path.read_text(encoding="utf-8").strip().splitlines()[0]
    return json.loads(line)


def test_solve_ils_writes_telemetry(tmp_path: Path):
    pb = _load_problem()
    telemetry_path = tmp_path / "ils_runs.jsonl"
    res = solve_ils(
        pb,
        iters=10,
        seed=11,
        telemetry_log=telemetry_path,
        telemetry_context={"scenario_path": "examples/minitoy/scenario.yaml"},
    )
    assert telemetry_path.exists()
    record = _read_first_record(telemetry_path)
    assert record["solver"] == "ils"
    assert record["status"] == "ok"
    assert record["run_id"] == res["meta"]["telemetry_run_id"]
    steps_path = res["meta"].get("telemetry_steps_path")
    assert steps_path
    assert Path(steps_path).exists()


def test_solve_tabu_writes_telemetry(tmp_path: Path):
    pb = _load_problem()
    telemetry_path = tmp_path / "tabu_runs.jsonl"
    res = solve_tabu(
        pb,
        iters=15,
        seed=5,
        telemetry_log=telemetry_path,
        telemetry_context={"scenario_path": "examples/minitoy/scenario.yaml"},
    )
    assert telemetry_path.exists()
    record = _read_first_record(telemetry_path)
    assert record["solver"] == "tabu"
    assert record["status"] == "ok"
    assert record["run_id"] == res["meta"]["telemetry_run_id"]
    steps_path = res["meta"].get("telemetry_steps_path")
    assert steps_path
    assert Path(steps_path).exists()
