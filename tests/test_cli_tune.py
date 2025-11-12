from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app

runner = CliRunner()


def test_tune_random_cli_runs_solver(tmp_path: Path):
    telemetry_log = tmp_path / "telemetry" / "runs.jsonl"

    result = runner.invoke(
        app,
        [
            "tune-random",
            "examples/minitoy/scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
            "--runs",
            "2",
            "--iters",
            "10",
            "--base-seed",
            "42",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert telemetry_log.exists()

    lines = telemetry_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["solver"] == "sa"
    assert first["schema_version"] == "1.1"
    assert "operator_weights" in result.stdout or "Operators" in result.stdout
    context = first.get("context", {})
    assert context.get("num_blocks") is not None
    assert context.get("num_machines") is not None

    steps_dir = telemetry_log.parent / "steps"
    assert steps_dir.exists()
    for entry in lines[:-1]:
        payload = json.loads(entry)
        run_id = payload.get("run_id")
        if isinstance(run_id, str):
            assert (steps_dir / f"{run_id}.jsonl").exists()
    summary = json.loads(lines[-1])
    assert summary["record_type"] == "tuner_summary"
    assert summary["algorithm"] == "random"
    sqlite_path = telemetry_log.with_suffix(".sqlite")
    assert sqlite_path.exists()
    first_run_id = first["run_id"]
    with sqlite3.connect(sqlite_path) as conn:
        metrics = conn.execute(
            "SELECT name, value FROM run_metrics WHERE run_id = ?", (first_run_id,)
        ).fetchall()
        assert metrics
        kpis = conn.execute(
            "SELECT name, value FROM run_kpis WHERE run_id = ?", (first_run_id,)
        ).fetchall()
        assert kpis
        summary_rows = conn.execute(
            "SELECT algorithm, summary_id, scenario_best_json FROM tuner_summaries"
        ).fetchall()
        assert summary_rows
        algo, summary_id, scenario_json = summary_rows[0]
        assert algo == "random"
        assert summary_id == summary["summary_id"]
        assert json.loads(scenario_json) == summary["scenario_best"]
    assert "summary_id" in summary
    assert "created_at" in summary


def test_tune_grid_cli_runs(tmp_path: Path):
    telemetry_log = tmp_path / "telemetry" / "runs.jsonl"

    result = runner.invoke(
        app,
        [
            "tune-grid",
            "examples/minitoy/scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
            "--batch-size",
            "1",
            "--batch-size",
            "2",
            "--preset",
            "balanced",
            "--preset",
            "explore",
            "--iters",
            "10",
            "--seed",
            "99",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert telemetry_log.exists()
    lines = telemetry_log.read_text(encoding="utf-8").strip().splitlines()
    # two presets * two batch sizes = four runs + one summary entry
    assert len(lines) == 5
    payload = json.loads(lines[0])
    assert payload["solver"] == "sa"
    context = payload.get("context", {})
    assert context.get("source") == "cli.tune-grid"
    assert context.get("batch_size") in {1, 2}
    summary = json.loads(lines[-1])
    assert summary["record_type"] == "tuner_summary"
    assert summary["algorithm"] == "grid"
    sqlite_path = telemetry_log.with_suffix(".sqlite")
    assert sqlite_path.exists()
    with sqlite3.connect(sqlite_path) as conn:
        row = conn.execute(
            "SELECT summary_id, scenario_best_json FROM tuner_summaries WHERE algorithm = 'grid'"
        ).fetchone()
    assert row is not None
    assert row[0] == summary["summary_id"]
    assert json.loads(row[1]) == summary["scenario_best"]
    assert "created_at" in summary


def test_tune_random_supports_bundle_alias(tmp_path: Path):
    telemetry_log = tmp_path / "telemetry" / "runs.jsonl"

    result = runner.invoke(
        app,
        [
            "tune-random",
            "--bundle",
            "baseline",
            "--telemetry-log",
            str(telemetry_log),
            "--runs",
            "1",
            "--iters",
            "10",
            "--base-seed",
            "999",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert telemetry_log.exists()
    lines = telemetry_log.read_text(encoding="utf-8").strip().splitlines()
    # two scenarios (minitoy, med42) -> two runs + summary record
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    run_records = [payload for payload in parsed if payload.get("record_type") == "run"]
    assert len(run_records) == 2
    bundle_members = set()
    for payload in run_records:
        context = payload.get("context") or {}
        assert context.get("bundle") == "baseline"
        member = context.get("bundle_member")
        assert member in {"minitoy", "med42"}
        bundle_members.add(member)
    assert bundle_members == {"minitoy", "med42"}

    summary = parsed[-1]
    assert summary["record_type"] == "tuner_summary"
    assert summary["algorithm"] == "random"
    assert set(summary["scenario_best"].keys()) == {"baseline:minitoy", "baseline:med42"}


def test_tune_bayes_cli_runs(tmp_path: Path):
    telemetry_log = tmp_path / "telemetry" / "runs.jsonl"

    result = runner.invoke(
        app,
        [
            "tune-bayes",
            "examples/minitoy/scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
            "--trials",
            "2",
            "--iters",
            "10",
            "--seed",
            "321",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert telemetry_log.exists()
    lines = telemetry_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    payload = json.loads(lines[0])
    assert payload["solver"] == "sa"
    context = payload.get("context", {})
    assert context.get("source") == "cli.tune-bayes"
    summary = json.loads(lines[-1])
    assert summary["record_type"] == "tuner_summary"
    assert summary["algorithm"] == "bayes"
    assert "summary_id" in summary
    assert "created_at" in summary
    sqlite_path = telemetry_log.with_suffix(".sqlite")
    assert sqlite_path.exists()
    with sqlite3.connect(sqlite_path) as conn:
        row = conn.execute(
            "SELECT summary_id, scenario_best_json FROM tuner_summaries WHERE algorithm = 'bayes'"
        ).fetchone()
        assert row is not None
        assert row[0] == summary["summary_id"]
        assert json.loads(row[1]) == summary["scenario_best"]
