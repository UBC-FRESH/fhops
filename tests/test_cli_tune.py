from __future__ import annotations

import json
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
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["solver"] == "sa"
    assert first["schema_version"] == "1.1"
    assert "operator_weights" in result.stdout or "Operators" in result.stdout
    context = first.get("context", {})
    assert context.get("num_blocks") is not None
    assert context.get("num_machines") is not None

    steps_dir = telemetry_log.parent / "steps"
    assert steps_dir.exists()
    for entry in lines:
        payload = json.loads(entry)
        run_id = payload.get("run_id")
        if isinstance(run_id, str):
            assert (steps_dir / f"{run_id}.jsonl").exists()


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
    # two presets * two batch sizes = four runs
    assert len(lines) == 4
    payload = json.loads(lines[0])
    assert payload["solver"] == "sa"
    context = payload.get("context", {})
    assert context.get("source") == "cli.tune-grid"
    assert context.get("batch_size") in {1, 2}
