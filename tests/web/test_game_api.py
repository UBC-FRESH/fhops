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
    assert payload["briefing"]["bec"] == "IDFdk3"
    assert payload["briefing"]["volume_m3_per_ha"] > 0


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


def test_game_shell_and_boundary(tmp_path: Path) -> None:
    client = _client(tmp_path)

    shell = client.get("/game")
    assert shell.status_code == 200
    assert "FHOPS Serious Game" in shell.text
    assert "level-map" in shell.text
    assert "const PAGE_BASE = window.location.pathname" in shell.text
    assert 'id="sawlog"' in shell.text
    assert 'id="landing"' in shell.text
    assert shell.headers.get("cache-control") == "no-store"
    boundary = client.get("/api/game/levels/kc_57254551/boundary")
    assert boundary.status_code == 200
    assert boundary.json()["type"] == "FeatureCollection"
    assert "best_choices" not in boundary.text


def test_multi_level_order_and_selector_payload(tmp_path: Path) -> None:
    app = create_app(
        ServiceConfig(
            roots=[tmp_path],
            workspace=Path.cwd(),
            game_levels=[
                Path("examples/game/levels/mkrf_684/level.yaml").resolve(),
                Path("examples/game/levels/gavin_1032/level.yaml").resolve(),
                LEVEL,
            ],
            game_precomputes=[
                Path("examples/game/precomputed/mkrf_684.json").resolve(),
                Path("examples/game/precomputed/gavin_1032.json").resolve(),
                PRECOMPUTE,
            ],
        )
    )
    client = TestClient(app)
    levels = client.get("/api/game/levels").json()
    assert [item["level_id"] for item in levels] == ["mkrf_684", "gavin_1032", "kc_57254551"]

    client.post("/api/game/sessions", json={"session_id": "multi"})
    client.post("/api/game/sessions/multi/teams", json={"team_code": "T1"})
    state = client.get("/api/game/sessions/multi/teams/T1").json()
    assert state["current_level"] == "mkrf_684"

    skipped = client.post(
        "/api/game/sessions/multi/teams/T1/submit?level_id=kc_57254551",
        json={
            "care_level": 0.0,
            "skidder_count": 1,
            "log_length_m": 6.1,
            "sawlog_min_dbh_cm": 20.0,
            "road_extension_m": 0.0,
        },
    )
    assert skipped.status_code == 400


def test_debrief_only_after_attempt(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/api/game/sessions", json={"session_id": "demo"})
    client.post("/api/game/sessions/demo/teams", json={"team_code": "T1"})
    before = client.get("/api/game/sessions/demo/teams/T1/debrief/kc_57254551")
    assert before.status_code == 400

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
    assert submitted.status_code == 200
    after = client.get("/api/game/sessions/demo/teams/T1/debrief/kc_57254551")
    assert after.status_code == 200
    payload = after.json()
    assert payload["optimal_choices"]["care_level"] == 0.5
    assert payload["explanation"]["source"] == "deterministic_template"


def test_game_debrief_uses_configured_agent_model_hook(tmp_path: Path) -> None:
    script = tmp_path / "fake_game_agent.py"
    script.write_text(
        "import json\nprint(json.dumps({'why_optimal': 'agent explanation', 'parameter_costs': {}}))\n",
        encoding="utf-8",
    )
    app = create_app(
        ServiceConfig(
            roots=[tmp_path],
            workspace=Path.cwd(),
            game_level=LEVEL,
            game_precompute=PRECOMPUTE,
            allow_agent=True,
            agent_command=(__import__("sys").executable, str(script)),
        )
    )
    client = TestClient(app)
    client.post("/api/game/sessions", json={"session_id": "agent"})
    client.post("/api/game/sessions/agent/teams", json={"team_code": "T1"})
    client.post(
        "/api/game/sessions/agent/teams/T1/submit",
        json={
            "care_level": 0.0,
            "skidder_count": 1,
            "log_length_m": 4.9,
            "sawlog_min_dbh_cm": 20.0,
            "road_extension_m": 0.0,
        },
    )
    debrief = client.get("/api/game/sessions/agent/teams/T1/debrief/kc_57254551")
    assert debrief.status_code == 200
    assert debrief.json()["explanation"]["source"] == "llm"
    assert debrief.json()["explanation"]["why_optimal"] == "agent explanation"


def test_leaderboard_endpoint(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/api/game/sessions", json={"session_id": "demo"})
    client.post("/api/game/sessions/demo/teams", json={"team_code": "T1"})
    leaderboard = client.get("/api/game/sessions/demo/leaderboard")
    assert leaderboard.status_code == 200
    assert leaderboard.json()[0]["team_code"] == "T1"
    assert leaderboard.json()[0]["completed_levels"] == 0


def test_final_chat_is_gated_until_completion(tmp_path: Path) -> None:
    script = tmp_path / "fake_chat_agent.py"
    script.write_text("print('final coach reply')\n", encoding="utf-8")
    app = create_app(
        ServiceConfig(
            roots=[tmp_path],
            workspace=Path.cwd(),
            game_level=LEVEL,
            game_precompute=PRECOMPUTE,
            allow_agent=True,
            agent_command=(__import__("sys").executable, str(script)),
        )
    )
    client = TestClient(app)
    assert client.get("/api/game/levels").json()[0]["chat_enabled"] is True
    client.post("/api/game/sessions", json={"session_id": "chat"})
    client.post("/api/game/sessions/chat/teams", json={"team_code": "T1"})

    blocked = client.post(
        "/api/game/sessions/chat/teams/T1/chat", json={"message": "How did we do?"}
    )
    assert blocked.status_code == 400

    client.post(
        "/api/game/sessions/chat/teams/T1/submit",
        json={
            "care_level": 0.5,
            "skidder_count": 1,
            "log_length_m": 6.1,
            "sawlog_min_dbh_cm": 20.0,
            "road_extension_m": 0.0,
        },
    )
    reply = client.post("/api/game/sessions/chat/teams/T1/chat", json={"message": "How did we do?"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["response"] == "final coach reply"


def test_contractor_and_consultant_fees_are_applied(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/api/game/sessions", json={"session_id": "fees"})
    client.post("/api/game/sessions/fees/teams", json={"team_code": "T1"})
    levels = client.get("/api/game/levels").json()[0]
    assert len(levels["contractors"]) == 4
    assert len(levels["consultants"]) == 3

    consulted = client.post(
        "/api/game/sessions/fees/teams/T1/consult",
        json={"consultant_ids": ["scout"]},
    )
    assert consulted.status_code == 200, consulted.text
    assert consulted.json()["tips"]
    assert consulted.json()["total_consultant_fees"] == 1500.0

    submitted = client.post(
        "/api/game/sessions/fees/teams/T1/submit",
        json={
            "contractor_id": "northpoint",
            "care_level": 0.5,
            "skidder_count": 1,
            "log_length_m": 6.1,
            "sawlog_min_dbh_cm": 20.0,
            "road_extension_m": 0.0,
        },
    )
    assert submitted.status_code == 200, submitted.text
    payload = submitted.json()
    assert payload["consultant_fees"] == 1500.0
    assert payload["result"]["consultant_fees"] == 1500.0
    assert payload["attempt"]["choices"]["contractor_id"] == "northpoint"
    debrief = client.get("/api/game/sessions/fees/teams/T1/debrief/kc_57254551")
    assert debrief.status_code == 200, debrief.text
    assert debrief.json()["consultant_fees"] == 1500.0
    assert debrief.json()["component_deltas"]["consultant_fees"] == -1500.0


def test_consultant_fees_can_drive_negative_score(tmp_path: Path) -> None:
    app = create_app(
        ServiceConfig(
            roots=[tmp_path],
            workspace=Path.cwd(),
            game_level=Path("examples/game/levels/gavin_1032/level.yaml").resolve(),
            game_precompute=Path("examples/game/precomputed/gavin_1032.json").resolve(),
        )
    )
    client = TestClient(app)
    client.post("/api/game/sessions", json={"session_id": "negative"})
    client.post("/api/game/sessions/negative/teams", json={"team_code": "T1"})
    consulted = client.post(
        "/api/game/sessions/negative/teams/T1/consult",
        json={"consultant_ids": ["scout", "planner", "specialist"]},
    )
    assert consulted.status_code == 200, consulted.text
    submitted = client.post(
        "/api/game/sessions/negative/teams/T1/submit",
        json={
            "contractor_id": "spot",
            "care_level": 0.0,
            "skidder_count": 2,
            "log_length_m": 4.9,
            "sawlog_min_dbh_cm": 20.0,
            "road_extension_m": 0.0,
        },
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["score"] < 0.0
