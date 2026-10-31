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


def test_web_game_flags_build_service_config(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_server(config):
        captured["config"] = config

    monkeypatch.setattr("fhops.web.app.run_server", fake_run_server)
    result = runner.invoke(
        app,
        [
            "web",
            "--runs",
            str(tmp_path),
            "--game-level",
            "examples/game/levels/mkrf_684/level.yaml",
            "--game-precompute",
            "examples/game/precomputed/mkrf_684.json",
            "--game-agent-model",
            "opencode-go/deepseek-v4.1-flash",
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    config = captured["config"]
    assert config.game_levels == [Path("examples/game/levels/mkrf_684/level.yaml")]
    assert config.game_precomputes == [Path("examples/game/precomputed/mkrf_684.json")]
    assert config.game_agent_model == "opencode-go/deepseek-v4.1-flash"
