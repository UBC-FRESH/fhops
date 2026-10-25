"""Security checks for bind, root, path, and assistant boundaries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fhops.web.app import ServiceConfig, create_app, validate_bind


def _client(tmp_path: Path, *, allow_agent: bool = False, script: Path | None = None) -> TestClient:
    (tmp_path / "scenario.yaml").write_text("name: test\n", encoding="utf-8")
    command = (sys.executable, str(script)) if script else ("opencode", "run")
    app = create_app(
        ServiceConfig(
            roots=[tmp_path / "runs"],
            workspace=tmp_path,
            allow_agent=allow_agent,
            agent_command=command,
        )
    )
    return TestClient(app)


def test_non_loopback_requires_explicit_remote_flag() -> None:
    with pytest.raises(ValueError, match="allow-remote"):
        validate_bind("0.0.0.0", allow_remote=False)
    validate_bind("0.0.0.0", allow_remote=True)
    validate_bind("127.0.0.1", allow_remote=False)


def test_static_and_scenario_traversal_are_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/static/../../etc/passwd").status_code == 404
    response = client.post(
        "/api/runs",
        json={
            "domain": "operational",
            "run_type": "solve_heur",
            "scenario": "../../etc/passwd",
        },
    )
    assert response.status_code == 400


def test_assistant_is_off_by_default(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post("/api/agent", json={"message": "hello"})
    assert response.status_code == 403
    assert "allow-agent" in response.json()["detail"]


def test_assistant_runs_only_with_flag(tmp_path: Path) -> None:
    script = tmp_path / "fake_agent.py"
    script.write_text(
        "import json\nprint(json.dumps({'text': 'assistant ok'}))\n", encoding="utf-8"
    )
    disabled = _client(tmp_path, allow_agent=False, script=script)
    assert disabled.post("/api/agent", json={"message": "hello"}).status_code == 403

    enabled = _client(tmp_path, allow_agent=True, script=script)
    response = enabled.post("/api/agent", json={"message": "hello"})
    assert response.status_code == 200, response.text
    assert response.json()["response"] == "assistant ok"
    too_long = enabled.post("/api/agent", json={"message": "x" * 5000})
    assert too_long.status_code == 422


def test_reviewer_skin_has_no_mutating_actions(tmp_path: Path) -> None:
    client = _client(tmp_path)
    reviewer = client.get("/api/skins/reviewer").json()
    assert reviewer["read_only"] is True
    assert "scenario" not in reviewer["panels"]
    assert "run" not in reviewer["panels"]
    assert not {
        "start_run",
        "pause",
        "stop",
        "edit_objective",
        "edit_locks",
        "edit_hauling",
        "edit_tactical",
    } & set(reviewer["actions"])


def test_health_reports_agent_state(tmp_path: Path) -> None:
    assert _client(tmp_path).get("/api/health").json()["agent_enabled"] is False
    script = tmp_path / "fake_agent.py"
    script.write_text("import json\nprint(json.dumps({'text': 'ok'}))\n", encoding="utf-8")
    assert (
        _client(tmp_path, allow_agent=True, script=script)
        .get("/api/health")
        .json()["agent_enabled"]
        is True
    )
