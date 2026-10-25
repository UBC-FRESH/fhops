"""CLI tests for `fhops web` discovery/manifest commands."""

from __future__ import annotations

import json
from pathlib import Path

from fhops.cli.main import app
from tests.cli import CliRunner, cli_text

runner = CliRunner()


def test_web_manifest_writes_run_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "haul_flows.csv").write_text("day\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["web", "manifest", str(run_dir), "--status", "ok"],
    )
    assert result.exit_code == 0, cli_text(result)
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["domain"] == "hauling"
    assert payload["run_type"] == "haul_plan"
    assert payload["status"] == "ok"


def test_web_discover_prints_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "op"
    run_dir.mkdir()
    (run_dir / "assignments.csv").write_text("machine_id\n", encoding="utf-8")
    result = runner.invoke(app, ["web", "discover", str(tmp_path)])
    assert result.exit_code == 0, cli_text(result)
    assert '"run_id": "op"' in cli_text(result)
    assert '"domain": "operational"' in cli_text(result)
