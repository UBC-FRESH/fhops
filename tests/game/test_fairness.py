"""P20 fairness and leakage checks for the stand game."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from fhops.game.stand_precompute import check_stand_precompute, load_stand_precompute
from fhops.web.app import ServiceConfig, create_app

LEVELS = [
    Path("examples/game/levels/mkrf_684/level.yaml"),
    Path("examples/game/levels/gavin_1032/level.yaml"),
    Path("examples/game/levels/kc_57254551/level.yaml"),
]
PRECOMPUTES = [
    Path("examples/game/precomputed/mkrf_684.json"),
    Path("examples/game/precomputed/gavin_1032.json"),
    Path("examples/game/precomputed/kc_57254551.json"),
]


def test_all_level_precomputes_are_complete_and_scored() -> None:
    for level_path, precompute_path in zip(LEVELS, PRECOMPUTES, strict=True):
        payload = load_stand_precompute(precompute_path)
        check_stand_precompute(level_path, payload)
        variants = payload["variants"]
        keys = {
            (
                record["care_level"],
                record["skidder_count"],
                record["log_length_m"],
                record["sawlog_min_dbh_cm"],
                record["road_extension_m"],
            )
            for record in variants
        }
        assert len(keys) == len(variants)
        assert payload["bounds"]["best_net_profit"] >= payload["bounds"]["worst_net_profit"]
        assert min(record["score"] for record in variants) >= 0.0
        assert max(record["score"] for record in variants) <= 100.0
        assert any(record["score"] == 100.0 for record in variants)


def test_public_payload_never_contains_best_choices() -> None:
    app = create_app(
        ServiceConfig(
            roots=[Path(".")],
            workspace=Path("."),
            game_levels=LEVELS,
            game_precomputes=PRECOMPUTES,
        )
    )
    client = TestClient(app)
    for response in (
        client.get("/api/game/levels"),
        client.get("/api/game/levels/kc_57254551/boundary"),
    ):
        assert response.status_code == 200
        assert "best_choices" not in json.dumps(response.json())


def test_same_choices_score_identically_for_two_teams(tmp_path: Path) -> None:
    app = create_app(
        ServiceConfig(
            roots=[tmp_path],
            workspace=Path("."),
            game_level=LEVELS[2],
            game_precompute=PRECOMPUTES[2],
        )
    )
    client = TestClient(app)
    client.post("/api/game/sessions", json={"session_id": "fair"})
    client.post("/api/game/sessions/fair/teams", json={"team_code": "A"})
    client.post("/api/game/sessions/fair/teams", json={"team_code": "B"})
    choices = {
        "care_level": 0.5,
        "skidder_count": 1,
        "log_length_m": 6.1,
        "sawlog_min_dbh_cm": 20.0,
        "road_extension_m": 0.0,
    }
    first = client.post("/api/game/sessions/fair/teams/A/submit", json=choices)
    second = client.post("/api/game/sessions/fair/teams/B/submit", json=choices)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["score"] == second.json()["score"]
    assert first.json()["attempt"]["net_profit"] == second.json()["attempt"]["net_profit"]
