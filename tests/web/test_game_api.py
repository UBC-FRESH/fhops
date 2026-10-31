"""Tests for the local serious-game API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from fhops.web.app import ServiceConfig, create_app

LEVEL = Path("examples/game/levels/kc_57254551/level.yaml").resolve()
PRECOMPUTE = Path("examples/game/precomputed/kc_57254551.json").resolve()


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        ServiceConfig(
            roots=[tmp_path],
            workspace=Path.cwd(),
            game_level=LEVEL,
            game_precompute=PRECOMPUTE,
        )
    )
    return TestClient(app)


def test_public_level_hides_optimal_choice(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/game/levels")

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["level_id"] == "kc_57254551"
    assert payload["status"] == "ready"
    assert "score_bounds" in payload
    assert "best_choices" not in payload
    assert "careful_logging" in payload
    assert "care_premium_per_m3_range" in payload["careful_logging"]


def test_session_team_and_submission(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = client.post("/api/game/sessions", json={"session_id": "demo"})
    assert created.status_code == 200

    registered = client.post("/api/game/sessions/demo/teams", json={"team_code": "T1"})
    assert registered.status_code == 200

    state = client.get("/api/game/sessions/demo/teams/T1")
    assert state.status_code == 200
    assert state.json()["current_level"] == "kc_57254551"
    assert state.json()["attempts"] == []

    submitted = client.post(
        "/api/game/sessions/demo/teams/T1/submit",
        json={
            "care_level": 0.0,
            "skidder_count": 2,
            "log_length_m": 4.9,
            "sawlog_min_dbh_cm": 20.0,
            "road_extension_m": 0.0,
        },
    )
    assert submitted.status_code == 200, submitted.text
    payload = submitted.json()
    assert 0.0 <= payload["score"] <= 100.0
    assert payload["attempt"]["level_id"] == "kc_57254551"
    assert "best_choices" not in payload

    state = client.get("/api/game/sessions/demo/teams/T1").json()
    assert state["current_level"] is None
    assert len(state["attempts"]) == 1

    replay = client.post(
        "/api/game/sessions/demo/teams/T1/submit",
        json={
            "care_level": 0.5,
            "skidder_count": 1,
            "log_length_m": 6.1,
            "sawlog_min_dbh_cm": 20.0,
            "road_extension_m": 0.0,
        },
    )
    assert replay.status_code == 400


def test_invalid_choice_fails_closed(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/api/game/sessions", json={"session_id": "demo"})
    client.post("/api/game/sessions/demo/teams", json={"team_code": "T1"})

    response = client.post(
        "/api/game/sessions/demo/teams/T1/submit",
        json={
            "care_level": 0.1,
            "skidder_count": 1,
            "log_length_m": 4.9,
            "sawlog_min_dbh_cm": 20.0,
            "road_extension_m": 0.0,
        },
    )
    assert response.status_code == 400
    assert "precomputed control grid" in response.json()["detail"]
