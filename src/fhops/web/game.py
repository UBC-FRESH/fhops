"""Local serious-game API: public level metadata, sessions, and scoring."""

from __future__ import annotations

import hashlib
import math
import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fhops.game.careful_logging import DEFAULT_CAREFUL_LOGGING_CURVE
from fhops.game.stand_precompute import (
    GameStandPrecomputeError,
    check_stand_precompute,
    load_stand_precompute,
)
from fhops.game.state import GameStateError, TournamentSession
from fhops.game.value import PriceSchedule

__all__ = ["GameService", "create_game_router"]


class GameSessionCreate(BaseModel):
    """Create a local game session."""

    session_id: str | None = None


class TeamCreate(BaseModel):
    """Register a team code."""

    team_code: str = Field(min_length=1, max_length=80)


class GameChoicesPayload(BaseModel):
    """Finite stand-control choices submitted by a team."""

    care_level: float
    skidder_count: int
    log_length_m: float
    sawlog_min_dbh_cm: float = 20.0
    road_extension_m: float = 0.0


class GameService:
    """Load a configured stand level and keep local tournament state."""

    def __init__(self, *, level_path: Path, precompute_path: Path) -> None:
        self.level_path = level_path.expanduser().resolve()
        self.precompute_path = precompute_path.expanduser().resolve()
        self.level = _load_level(self.level_path)
        self.precompute = load_stand_precompute(self.precompute_path)
        try:
            check_stand_precompute(self.level_path, self.precompute)
        except GameStandPrecomputeError as exc:
            raise ValueError(str(exc)) from exc
        self.price = PriceSchedule.from_path(
            (self.level_path.parent / self.level["prices"]).resolve()
        )
        self.level_id = str(self.level["level_id"])
        self.ruleset_hash = hashlib.sha256(
            self.level_path.read_bytes() + self.precompute_path.read_bytes()
        ).hexdigest()
        self.sessions: dict[str, TournamentSession] = {}

    def create_session(self, session_id: str | None = None) -> dict[str, Any]:
        """Create an empty local tournament session."""
        session_id = session_id or f"game-{secrets.token_hex(4)}"
        if session_id in self.sessions:
            raise ValueError(f"Session {session_id!r} already exists.")
        session = TournamentSession.create(
            session_id,
            (self.level_id,),
            self.ruleset_hash,
        )
        self.sessions[session_id] = session
        return session.to_dict()

    def session(self, session_id: str) -> TournamentSession:
        """Return a session or raise a not-found error."""
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"Unknown session {session_id!r}") from exc

    def register_team(self, session_id: str, team_code: str) -> dict[str, Any]:
        """Register one team in a session."""
        session = self.session(session_id)
        team = session.register_team(team_code)
        return team.to_dict()

    def public_level(self) -> dict[str, Any]:
        """Return pre-run level metadata without the optimal choice."""
        bounds = self.precompute["bounds"]
        bucking = self.level.get("bucking", {})
        return {
            "level_id": self.level_id,
            "name": self.level["name"],
            "order": self.level.get("order", 0),
            "area_ha": self.level.get("area_ha"),
            "difficulty": self.level.get("difficulty"),
            "controls": {
                "care_levels": self.level["care_levels"],
                "skidder_counts": self.level["skidder_counts"],
                "log_length_m": bucking.get("log_length_m", []),
                "sawlog_min_dbh_cm": bucking.get("sawlog_min_dbh_cm", []),
                "landing_options": self.level.get("landing_options", {}),
            },
            "careful_logging": DEFAULT_CAREFUL_LOGGING_CURVE.public_summary(),
            "prices": {
                "currency": self.price.currency,
                "products": dict(self.price.products),
                "mobilisation_cost": self.price.mobilisation_cost,
                "road_extension_cost_per_m": self.price.road_extension_cost_per_m,
            },
            "score_bounds": {
                "best_net_profit": bounds["best_net_profit"],
                "worst_net_profit": bounds["worst_net_profit"],
            },
            "status": "ready",
        }

    def team_state(self, session_id: str, team_code: str) -> dict[str, Any]:
        """Return a team's current level and attempts without optimal controls."""
        session = self.session(session_id)
        team = session.team(team_code)
        return {
            "session_id": session.session_id,
            "team_code": team.team_code,
            "current_level": session.current_level(team.team_code),
            "attempts": [attempt.to_dict() for attempt in team.attempts],
            "total_score": team.total_score,
        }

    def leaderboard(self, session_id: str) -> list[dict[str, Any]]:
        """Return the session leaderboard."""
        return self.session(session_id).leaderboard()

    def submit(
        self,
        session_id: str,
        team_code: str,
        *,
        level_id: str,
        choices: GameChoicesPayload,
    ) -> dict[str, Any]:
        """Score a precomputed choice and record the attempt."""
        session = self.session(session_id)
        variant = self._find_variant(choices)
        attempt = session.submit(
            team_code=team_code,
            level_id=level_id,
            choices=choices.model_dump(),
            net_profit=float(variant["net_profit"]),
            score=float(variant["score"]),
        )
        return {
            "attempt": attempt.to_dict(),
            "score": attempt.score,
            "result": variant["result"],
        }

    def _find_variant(self, choices: GameChoicesPayload) -> dict[str, Any]:
        for record in self.precompute["variants"]:
            if (
                math.isclose(float(record["care_level"]), choices.care_level, abs_tol=1e-9)
                and int(record["skidder_count"]) == choices.skidder_count
                and math.isclose(float(record["log_length_m"]), choices.log_length_m, abs_tol=1e-9)
                and math.isclose(
                    float(record["sawlog_min_dbh_cm"]),
                    choices.sawlog_min_dbh_cm,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(record["road_extension_m"]),
                    choices.road_extension_m,
                    abs_tol=1e-9,
                )
            ):
                return record
        raise ValueError("Submitted choices are not in the precomputed control grid.")


def _load_level(path: Path) -> dict[str, Any]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "fhops.game.level.v1":
        raise ValueError(f"Unsupported game level manifest: {path}")
    return payload


def create_game_router(service: GameService) -> APIRouter:
    """Create game routes for one configured stand level."""
    router = APIRouter(prefix="/api/game", tags=["game"])

    @router.get("/levels")
    def levels() -> list[dict[str, Any]]:
        return [service.public_level()]

    @router.post("/sessions")
    def create_session(request: GameSessionCreate) -> dict[str, Any]:
        try:
            return service.create_session(request.session_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/sessions/{session_id}/leaderboard")
    def leaderboard(session_id: str) -> list[dict[str, Any]]:
        try:
            return service.leaderboard(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/sessions/{session_id}/teams")
    def register_team(session_id: str, request: TeamCreate) -> dict[str, Any]:
        try:
            return service.register_team(session_id, request.team_code)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GameStateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/sessions/{session_id}/teams/{team_code}")
    def team_state(session_id: str, team_code: str) -> dict[str, Any]:
        try:
            return service.team_state(session_id, team_code)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GameStateError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/sessions/{session_id}/teams/{team_code}/submit")
    def submit(
        session_id: str,
        team_code: str,
        request: GameChoicesPayload,
        level_id: str | None = None,
    ) -> dict[str, Any]:
        target_level = level_id or service.level_id
        try:
            return service.submit(
                session_id,
                team_code,
                level_id=target_level,
                choices=request,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (GameStateError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
