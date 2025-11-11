from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app

runner = CliRunner()


def test_tune_random_cli_stub(tmp_path: Path):
    telemetry_log = tmp_path / "runs.jsonl"
    record = {
        "record_type": "run",
        "run_id": "abc123",
        "solver": "sa",
        "scenario": "minitoy",
        "status": "ok",
        "metrics": {"objective": 123.45},
        "duration_seconds": 1.23,
    }
    telemetry_log.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "tune-random",
            "examples/minitoy/scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
            "--samples",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Random tuner stub" in result.stdout
    assert "abc123" in result.stdout
