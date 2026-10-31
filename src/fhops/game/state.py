"""Local tournament state with one-play and level-order enforcement."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "GameStateError",
    "LevelAttempt",
    "TeamState",
    "TournamentSession",
]


class GameStateError(ValueError):
    """Raised when a tournament transition is invalid."""


@dataclass(frozen=True, slots=True)
class LevelAttempt:
    """One immutable attempt for a team and level."""

    level_id: str
    choices: dict[str, Any]
    net_profit: float
    score: float

    def __post_init__(self) -> None:
        if not self.level_id.strip():
            raise ValueError("level_id must not be blank.")
        if not self.choices:
            raise ValueError("choices must not be empty.")
        if not math.isfinite(self.net_profit):
            raise ValueError("net_profit must be finite.")
        if not 0.0 <= self.score <= 100.0:
            raise ValueError("score must be within 0–100.")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable attempt."""
        return {
            "level_id": self.level_id,
            "choices": dict(self.choices),
            "net_profit": self.net_profit,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LevelAttempt:
        """Load an attempt from a JSON mapping."""
        return cls(
            level_id=str(payload["level_id"]),
            choices=dict(payload["choices"]),
            net_profit=float(payload["net_profit"]),
            score=float(payload["score"]),
        )


@dataclass
class TeamState:
    """Ordered attempts for one team."""

    team_code: str
    attempts: list[LevelAttempt] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        """Return the sum of completed attempt scores."""
        return sum(attempt.score for attempt in self.attempts)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable team state."""
        return {
            "team_code": self.team_code,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TeamState:
        """Load a team state from JSON."""
        return cls(
            team_code=str(payload["team_code"]),
            attempts=[LevelAttempt.from_dict(item) for item in payload.get("attempts", [])],
        )


@dataclass
class TournamentSession:
    """A local instructor-run tournament."""

    session_id: str
    level_order: tuple[str, ...]
    ruleset_hash: str
    teams: dict[str, TeamState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must not be blank.")
        if not self.level_order or len(set(self.level_order)) != len(self.level_order):
            raise ValueError("level_order must be non-empty and unique.")
        if not self.ruleset_hash.strip():
            raise ValueError("ruleset_hash must not be blank.")

    @classmethod
    def create(
        cls,
        session_id: str,
        level_order: tuple[str, ...],
        ruleset_hash: str,
    ) -> TournamentSession:
        """Create an empty tournament session."""
        return cls(session_id=session_id, level_order=level_order, ruleset_hash=ruleset_hash)

    def register_team(self, team_code: str) -> TeamState:
        """Register a team once."""
        normalized = team_code.strip()
        if not normalized:
            raise GameStateError("team_code must not be blank.")
        if normalized in self.teams:
            raise GameStateError(f"Team {normalized!r} is already registered.")
        team = TeamState(team_code=normalized)
        self.teams[normalized] = team
        return team

    def team(self, team_code: str) -> TeamState:
        """Return a registered team or raise a state error."""
        return self._team(team_code)

    def current_level(self, team_code: str) -> str | None:
        """Return the next required level for a team."""
        team = self._team(team_code)
        attempted = {attempt.level_id for attempt in team.attempts}
        for level_id in self.level_order:
            if level_id not in attempted:
                return level_id
        return None

    def submit(
        self,
        *,
        team_code: str,
        level_id: str,
        choices: dict[str, Any],
        net_profit: float,
        score: float,
    ) -> LevelAttempt:
        """Record one attempt, enforcing order and no replay."""
        team = self._team(team_code)
        if level_id not in self.level_order:
            raise GameStateError(f"Unknown level {level_id!r}.")
        if any(attempt.level_id == level_id for attempt in team.attempts):
            raise GameStateError(f"Level {level_id!r} has already been played by this team.")
        expected = self.current_level(team_code)
        if expected != level_id:
            raise GameStateError(f"Expected level {expected!r} next; refused {level_id!r}.")
        attempt = LevelAttempt(
            level_id=level_id,
            choices=dict(choices),
            net_profit=float(net_profit),
            score=float(score),
        )
        team.attempts.append(attempt)
        return attempt

    def leaderboard(self) -> list[dict[str, Any]]:
        """Return teams ordered by total score, then team code."""
        rows = [
            {
                "team_code": team.team_code,
                "total_score": team.total_score,
                "completed_levels": len(team.attempts),
            }
            for team in self.teams.values()
        ]
        return sorted(rows, key=lambda row: (-row["total_score"], row["team_code"]))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable tournament state."""
        return {
            "schema_version": "fhops.game.tournament.v1",
            "session_id": self.session_id,
            "level_order": list(self.level_order),
            "ruleset_hash": self.ruleset_hash,
            "teams": [team.to_dict() for team in self.teams.values()],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TournamentSession:
        """Load a tournament state from JSON."""
        if payload.get("schema_version") != "fhops.game.tournament.v1":
            raise GameStateError("Unsupported tournament-state schema.")
        session = cls(
            session_id=str(payload["session_id"]),
            level_order=tuple(str(item) for item in payload["level_order"]),
            ruleset_hash=str(payload["ruleset_hash"]),
        )
        for item in payload.get("teams", []):
            team = TeamState.from_dict(item)
            session.teams[team.team_code] = team
        return session

    def save(self, path: str | Path) -> None:
        """Persist the tournament state as stable JSON."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> TournamentSession:
        """Load a persisted tournament state."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def _team(self, team_code: str) -> TeamState:
        normalized = team_code.strip()
        try:
            return self.teams[normalized]
        except KeyError as exc:
            raise GameStateError(f"Unknown team {normalized!r}.") from exc
