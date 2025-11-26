from __future__ import annotations

import csv
from pathlib import Path

import pytest

from fhops.cli.main import app

from .cli import CliRunner

runner = CliRunner()


@pytest.mark.milp_refactor
def test_telemetry_report_generates_outputs(tmp_path: Path):
    telemetry_log = tmp_path / "telemetry" / "runs.jsonl"
    sqlite_path = telemetry_log.with_suffix(".sqlite")

    result = runner.invoke(
        app,
        [
            "tune-random",
            "examples/minitoy/scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
            "--runs",
            "1",
            "--iters",
            "10",
        ],
    )
    assert result.exit_code == 0, result.stdout

    result = runner.invoke(
        app,
        [
            "tune-grid",
            "examples/minitoy/scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
            "--batch-size",
            "1",
            "--preset",
            "balanced",
            "--iters",
            "10",
            "--seed",
            "13",
        ],
    )
    assert result.exit_code == 0, result.stdout

    result = runner.invoke(
        app,
        [
            "tune-bayes",
            "examples/minitoy/scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
            "--trials",
            "1",
            "--iters",
            "10",
            "--seed",
            "7",
        ],
    )
    assert result.exit_code == 0, result.stdout

    assert sqlite_path.exists()

    csv_path = tmp_path / "report.csv"
    md_path = tmp_path / "report.md"

    result = runner.invoke(
        app,
        [
            "telemetry",
            "report",
            str(sqlite_path),
            "--out-csv",
            str(csv_path),
            "--out-markdown",
            str(md_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert csv_path.exists()
    assert md_path.exists()

    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    algorithms = {row["algorithm"] for row in rows}
    assert {"random", "grid", "bayes"} <= algorithms
    for row in rows:
        assert row["scenario"]
        if row["summary_best"]:
            float(row["summary_best"])
        assert "machine_costs_summary" in row
        assert "repair_usage_alert" in row

    markdown = md_path.read_text(encoding="utf-8")
    assert "| Algorithm | Scenario |" in markdown
    assert "| random |" in markdown.lower() or "| Random |" in markdown
