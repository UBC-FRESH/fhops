"""Tests for local tournament order, replay, and persistence rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.game.state import GameStateError, TournamentSession


def _session() -> TournamentSession:
    session = TournamentSession.create("demo", ("L1", "L2", "L3"), "ruleset-1")
    session.register_team("TEAM-A")
    return session


def test_submit_enforces_order_and_one_play() -> None:
    session = _session()

    with pytest.raises(GameStateError, match="Expected level 'L1'"):
        session.submit(
            team_code="TEAM-A",
            level_id="L2",
            choices={"care": 0.5},
            net_profit=10.0,
            score=50.0,
        )

    session.submit(
        team_code="TEAM-A",
        level_id="L1",
        choices={"care": 0.5},
        net_profit=10.0,
        score=50.0,
    )
    with pytest.raises(GameStateError, match="already been played"):
        session.submit(
            team_code="TEAM-A",
            level_id="L1",
            choices={"care": 0.25},
            net_profit=11.0,
            score=60.0,
        )
    assert session.current_level("TEAM-A") == "L2"


def test_unknown_team_and_level_fail_closed() -> None:
    session = _session()

    with pytest.raises(GameStateError, match="Unknown team"):
        session.current_level("NOPE")
    with pytest.raises(GameStateError, match="Unknown level"):
        session.submit(
            team_code="TEAM-A",
            level_id="NOPE",
            choices={"care": 0.5},
            net_profit=1.0,
            score=1.0,
        )


def test_leaderboard_and_roundtrip(tmp_path: Path) -> None:
    session = _session()
    session.register_team("TEAM-B")
    session.submit(
        team_code="TEAM-A",
        level_id="L1",
        choices={"care": 0.5},
        net_profit=10.0,
        score=70.0,
    )
    session.submit(
        team_code="TEAM-B",
        level_id="L1",
        choices={"care": 0.25},
        net_profit=8.0,
        score=60.0,
    )
    path = tmp_path / "tournament.json"
    session.save(path)
    loaded = TournamentSession.load(path)

    assert loaded.to_dict() == session.to_dict()
    assert loaded.leaderboard()[0] == {
        "team_code": "TEAM-A",
        "total_score": 70.0,
        "completed_levels": 1,
    }
