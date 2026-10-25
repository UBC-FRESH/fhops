"""Tests for the optional FastAPI service skeleton."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fhops.web.app import ServiceConfig, create_app, is_loopback, validate_bind


def _run_dir(root: Path, name: str, *files: str) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename in files:
        (run_dir / filename).write_text("value\n", encoding="utf-8")
    return run_dir


def test_health_and_run_discovery(tmp_path: Path) -> None:
    _run_dir(tmp_path, "op", "assignments.csv")
    _run_dir(tmp_path, "haul", "haul_flows.csv")
    app = create_app(ServiceConfig(roots=[tmp_path], host="127.0.0.1"))
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    payload = runs.json()
    assert {row["run_id"] for row in payload} == {"op", "haul"}
    assert {row["domain"] for row in payload} == {"operational", "hauling"}

    detail = client.get("/api/runs/haul")
    assert detail.status_code == 200
    assert detail.json()["domain"] == "hauling"

    missing = client.get("/api/runs/nope")
    assert missing.status_code == 404


def test_static_shell(tmp_path: Path) -> None:
    app = create_app(ServiceConfig(roots=[tmp_path], host="127.0.0.1"))
    client = TestClient(app)
    index = client.get("/")
    assert index.status_code == 200
    assert "FHOPS" in index.text
    assert client.get("/static/style.css").status_code == 200


def test_remote_bind_is_refused_without_opt_in() -> None:
    assert is_loopback("127.0.0.1")
    assert is_loopback("localhost")
    assert not is_loopback("0.0.0.0")
    validate_bind("127.0.0.1", allow_remote=False)
    with pytest.raises(ValueError, match="non-loopback"):
        validate_bind("0.0.0.0", allow_remote=False)
    validate_bind("0.0.0.0", allow_remote=True)
    with pytest.raises(ValueError, match="non-loopback"):
        create_app(ServiceConfig(roots=[Path.cwd()], host="0.0.0.0"))
