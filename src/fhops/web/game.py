"""Local serious-game API: public level metadata, sessions, and scoring."""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fhops.game.careful_logging import DEFAULT_CAREFUL_LOGGING_CURVE
from fhops.game.debrief import build_debrief_facts, explain_debrief_cached
from fhops.game.explain_cache import ExplanationCache
from fhops.game.replay import generate_replay
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


class ChatRequest(BaseModel):
    """Final-debrief chat message."""

    message: str = Field(min_length=1, max_length=4000)


class ConsultRequest(BaseModel):
    """Paid consultant tips requested before submission."""

    consultant_ids: list[str] = Field(default_factory=list, max_length=3)


class GameChoicesPayload(BaseModel):
    """Finite stand-control choices submitted by a team."""

    contractor_id: str | None = None
    care_level: float
    skidder_count: int
    log_length_m: float
    sawlog_min_dbh_cm: float = 20.0
    road_extension_m: float = 0.0


@dataclass(frozen=True, slots=True)
class _StandEntry:
    """Loaded stand level and its complete precompute."""

    level_path: Path
    precompute_path: Path
    level: dict[str, Any]
    precompute: dict[str, Any]
    price: PriceSchedule
    level_id: str
    order: int

    @property
    def ruleset_hash(self) -> str:
        return hashlib.sha256(
            self.level_path.read_bytes() + self.precompute_path.read_bytes()
        ).hexdigest()


class GameService:
    """Load configured stand levels and keep local tournament state."""

    def __init__(
        self,
        *,
        level_path: Path | None = None,
        precompute_path: Path | None = None,
        levels: list[tuple[Path, Path]] | None = None,
        llm_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        chat_fn: Callable[[dict[str, Any], str], str] | None = None,
        explanation_cache: ExplanationCache | None = None,
        session_store: Path | None = None,
    ) -> None:
        specs = list(levels or [])
        if level_path is not None or precompute_path is not None:
            if level_path is None or precompute_path is None:
                raise ValueError("game_level and game_precompute must be configured together.")
            specs.append((level_path, precompute_path))
        if not specs:
            raise ValueError("At least one stand level is required.")
        entries: dict[str, _StandEntry] = {}
        for spec_level, spec_precompute in specs:
            level_path_resolved = spec_level.expanduser().resolve()
            precompute_path_resolved = spec_precompute.expanduser().resolve()
            level = _load_level(level_path_resolved)
            precompute = load_stand_precompute(precompute_path_resolved)
            try:
                check_stand_precompute(level_path_resolved, precompute)
            except GameStandPrecomputeError as exc:
                raise ValueError(str(exc)) from exc
            level_id = str(level["level_id"])
            if level_id in entries:
                raise ValueError(f"Duplicate game level {level_id!r}.")
            entries[level_id] = _StandEntry(
                level_path=level_path_resolved,
                precompute_path=precompute_path_resolved,
                level=level,
                precompute=precompute,
                price=PriceSchedule.from_path(
                    (level_path_resolved.parent / level["prices"]).resolve()
                ),
                level_id=level_id,
                order=int(level.get("order", 0)),
            )
        self.entries = entries
        self.level_order = tuple(
            entry.level_id for entry in sorted(entries.values(), key=lambda item: item.order)
        )
        self.ruleset_hash = hashlib.sha256(
            b"".join(
                entries[level_id].level_path.read_bytes()
                + entries[level_id].precompute_path.read_bytes()
                for level_id in self.level_order
            )
        ).hexdigest()
        self.sessions: dict[str, TournamentSession] = {}
        self.session_store = session_store.expanduser().resolve() if session_store else None
        if self.session_store is not None and self.session_store.is_file():
            stored = json.loads(self.session_store.read_text(encoding="utf-8"))
            if stored.get("schema_version") != "fhops.game.sessions.v1":
                raise ValueError("Unsupported game session store schema.")
            for item in stored.get("sessions", []):
                session = TournamentSession.from_dict(item)
                self.sessions[session.session_id] = session
        self.replay_tokens: dict[str, Path] = {}
        self.replay_jobs: dict[str, dict[str, Any]] = {}
        self.replay_locks: dict[Path, threading.Lock] = {}
        self.replay_locks_guard = threading.Lock()
        self.llm_fn = llm_fn
        self.chat_fn = chat_fn
        self.explanation_cache = explanation_cache

    @property
    def level_id(self) -> str:
        """Return the first level id for single-level compatibility."""
        return self.level_order[0]

    def create_session(self, session_id: str | None = None) -> dict[str, Any]:
        """Create an empty local tournament session in level order."""
        session_id = session_id or f"game-{secrets.token_hex(4)}"
        if session_id in self.sessions:
            raise ValueError(f"Session {session_id!r} already exists.")
        session = TournamentSession.create(
            session_id,
            self.level_order,
            self.ruleset_hash,
        )
        self.sessions[session_id] = session
        self._persist_sessions()
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
        self._persist_sessions()
        return team.to_dict()

    def boundary(self, level_id: str) -> dict[str, Any]:
        """Return a stand boundary for the whole-operation viewport."""
        import json

        entry = self._entry(level_id)
        path = (entry.level_path.parent / entry.level["boundary"]).resolve()
        return json.loads(path.read_text(encoding="utf-8"))

    def public_levels(self) -> list[dict[str, Any]]:
        """Return all public level metadata in order."""
        return [self.public_level(level_id) for level_id in self.level_order]

    def public_level(self, level_id: str | None = None) -> dict[str, Any]:
        """Return pre-run level metadata without the optimal choice."""
        entry = self._entry(level_id or self.level_id)
        bucking = entry.level.get("bucking", {})
        return {
            "level_id": entry.level_id,
            "name": entry.level["name"],
            "order": entry.order,
            "area_ha": entry.level.get("area_ha"),
            "difficulty": entry.level.get("difficulty"),
            "briefing": entry.level.get("briefing", {}),
            "contractors": entry.level.get("contractors", []),
            "consultants": entry.level.get("consultants", []),
            "max_consultants": entry.level.get("max_consultants", 3),
            "controls": {
                "care_levels": entry.level["care_levels"],
                "skidder_counts": entry.level["skidder_counts"],
                "log_length_m": bucking.get("log_length_m", []),
                "sawlog_min_dbh_cm": bucking.get("sawlog_min_dbh_cm", []),
                "landing_options": entry.level.get("landing_options", {}),
            },
            "careful_logging": (
                DEFAULT_CAREFUL_LOGGING_CURVE.public_summary()
                if entry.level.get("selection_cut", True)
                else None
            ),
            "prices": {
                "currency": entry.price.currency,
                "products": dict(entry.price.products),
                "mobilisation_cost": entry.price.mobilisation_cost,
                "road_extension_cost_per_m": entry.price.road_extension_cost_per_m,
            },
            "score_bounds": self._adjusted_bounds(entry),
            "chat_enabled": self.chat_fn is not None,
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
            "consultants": {key: list(value) for key, value in team.consultants.items()},
            "total_score": team.total_score,
        }

    def leaderboard(self, session_id: str) -> list[dict[str, Any]]:
        """Return the session leaderboard."""
        return self.session(session_id).leaderboard()

    def debrief(
        self,
        session_id: str,
        team_code: str,
        level_id: str,
    ) -> dict[str, Any]:
        """Return a post-attempt debrief, including the optimal choice."""
        session = self.session(session_id)
        team = session.team(team_code)
        attempt = next(
            (item for item in team.attempts if item.level_id == level_id),
            None,
        )
        if attempt is None:
            raise ValueError(f"Level {level_id!r} has not been completed by this team.")
        entry = self._entry(level_id)
        facts = build_debrief_facts(
            entry.precompute,
            player_choices=attempt.choices,
            score=attempt.score,
        )
        contractor = self._contractor(
            entry,
            str(attempt.choices.get("contractor_id") or ""),
        )
        variant = self._find_variant(
            entry,
            GameChoicesPayload(
                **{
                    key: attempt.choices[key]
                    for key in GameChoicesPayload.model_fields
                    if key in attempt.choices
                }
            ),
        )
        adjustment = self._contractor_adjustment(contractor, variant["result"])
        fees = self._consultant_fees(
            entry, [str(item) for item in attempt.choices.get("consultant_ids", [])]
        )
        component_deltas = dict(facts.component_deltas)
        component_deltas["contractor_adjustment"] = adjustment
        component_deltas["consultant_fees"] = -fees
        facts = replace(
            facts,
            player_net_profit=attempt.net_profit,
            component_deltas=component_deltas,
        )
        return {
            **facts.to_dict(),
            "contractor": contractor,
            "consultant_fees": fees,
            "explanation": explain_debrief_cached(
                facts,
                cache=self.explanation_cache,
                llm_fn=self.llm_fn,
            ),
        }

    def chat(self, session_id: str, team_code: str, message: str) -> dict[str, Any]:
        """Chat about the completed tournament; only after the final level."""
        session = self.session(session_id)
        team = session.team(team_code)
        if session.current_level(team.team_code) is not None:
            raise GameStateError("Final chat unlocks only after the final level is complete.")
        if self.chat_fn is None:
            raise GameStateError("The optional final chat agent is disabled.")
        if not message.strip():
            raise ValueError("Chat message must not be blank.")
        debriefs = []
        for attempt in team.attempts:
            entry = self._entry(attempt.level_id)
            facts = build_debrief_facts(
                entry.precompute,
                player_choices=attempt.choices,
                score=attempt.score,
            )
            debriefs.append(facts.to_dict())
        context = {
            "team_code": team.team_code,
            "total_score": team.total_score,
            "attempts": [attempt.to_dict() for attempt in team.attempts],
            "debriefs": debriefs,
        }
        return {"response": self.chat_fn(context, message), "source": "agent"}

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
        team = session.team(team_code)
        entry = self._entry(level_id)
        variant = self._find_variant(entry, choices)
        contractor = self._contractor(entry, choices.contractor_id)
        base_result = variant["result"]
        contractor_adjustment = self._contractor_adjustment(contractor, base_result)
        consultant_ids = team.consultants.get(level_id, [])
        consultant_fees = self._consultant_fees(entry, consultant_ids)
        net_profit = float(variant["net_profit"]) + contractor_adjustment - consultant_fees
        bounds = self._adjusted_bounds(entry)
        best = float(bounds["best_net_profit"])
        worst = float(bounds["worst_net_profit"])
        span = best - worst
        score = 100.0 if not span else 100.0 * (net_profit - worst) / span
        score = min(100.0, score)
        attempt_choices = choices.model_dump()
        attempt_choices["contractor_id"] = contractor["id"]
        attempt_choices["consultant_ids"] = list(consultant_ids)
        attempt = session.submit(
            team_code=team_code,
            level_id=entry.level_id,
            choices=attempt_choices,
            net_profit=net_profit,
            score=score,
        )
        self._persist_sessions()
        result_payload = dict(base_result)
        result_payload["net_profit"] = net_profit
        result_payload["contractor_adjustment"] = contractor_adjustment
        result_payload["consultant_fees"] = consultant_fees
        return {
            "attempt": attempt.to_dict(),
            "score": attempt.score,
            "contractor": contractor,
            "consultant_fees": consultant_fees,
            "result": result_payload,
        }

    def consult(self, session_id: str, team_code: str, consultant_ids: list[str]) -> dict[str, Any]:
        """Purchase paid tips for the current level and return their text."""
        session = self.session(session_id)
        team = session.team(team_code)
        current = session.current_level(team.team_code)
        if current is None:
            raise GameStateError("All levels are complete; no further tips are available.")
        entry = self._entry(current)
        by_id = {str(item["id"]): item for item in entry.level.get("consultants", [])}
        selected = list(dict.fromkeys(consultant_ids))
        if not selected:
            raise ValueError("Select at least one consultant.")
        if len(selected) > int(entry.level.get("max_consultants", 3)):
            raise ValueError("Too many consultants selected.")
        existing = list(team.consultants.get(current, []))
        combined = list(dict.fromkeys(existing + selected))
        if len(combined) > int(entry.level.get("max_consultants", 3)):
            raise ValueError("Too many consultants selected for this level.")
        unknown = [item for item in combined if item not in by_id]
        if unknown:
            raise ValueError("Unknown consultant(s): " + ", ".join(unknown))
        team.consultants[current] = combined
        self._persist_sessions()
        tips = []
        for consultant_id in selected:
            tips.extend(self._tip_text(entry, by_id[consultant_id]))
        return {
            "level_id": current,
            "consultant_ids": combined,
            "tips": tips,
            "total_consultant_fees": self._consultant_fees(entry, combined),
        }

    def _persist_sessions(self) -> None:
        if self.session_store is None:
            return
        self.session_store.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "fhops.game.sessions.v1",
            "sessions": [session.to_dict() for session in self.sessions.values()],
        }
        self.session_store.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def replay(self, session_id: str, team_code: str, level_id: str) -> dict[str, Any]:
        """Start asynchronous generation of optimal and player replays."""
        session = self.session(session_id)
        team = session.team(team_code)
        attempt = next((item for item in team.attempts if item.level_id == level_id), None)
        if attempt is None:
            raise GameStateError(f"Level {level_id!r} has not been completed by this team.")
        job_id = secrets.token_urlsafe(16)
        self.replay_jobs[job_id] = {"status": "running", "level_id": level_id, "error": None}
        thread = threading.Thread(
            target=self._run_replay_job,
            args=(job_id, session_id, team_code, level_id),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id, "status": "running"}

    def _run_replay_job(self, job_id: str, session_id: str, team_code: str, level_id: str) -> None:
        try:
            payload = self._build_replay_assets(session_id, team_code, level_id)
            self.replay_jobs[job_id] = {"status": "ready", "result": payload, "error": None}
        except Exception as exc:  # noqa: BLE001 - background job reports its failure
            self.replay_jobs[job_id] = {"status": "failed", "error": str(exc)}

    def replay_status(self, job_id: str) -> dict[str, Any]:
        """Return the status of an asynchronous replay job."""
        try:
            return dict(self.replay_jobs[job_id])
        except KeyError as exc:
            raise KeyError(f"Unknown replay job {job_id!r}") from exc

    def _build_replay_assets(
        self, session_id: str, team_code: str, level_id: str
    ) -> dict[str, Any]:
        session = self.session(session_id)
        team = session.team(team_code)
        attempt = next((item for item in team.attempts if item.level_id == level_id), None)
        if attempt is None:
            raise GameStateError(f"Level {level_id!r} has not been completed by this team.")
        entry = self._entry(level_id)
        optimal_choices = {
            key: entry.precompute["bounds"]["best_choices"][key]
            for key in (
                "care_level",
                "skidder_count",
                "log_length_m",
                "sawlog_min_dbh_cm",
                "road_extension_m",
            )
        }
        player_choices = {
            key: attempt.choices[key]
            for key in (
                "care_level",
                "skidder_count",
                "log_length_m",
                "sawlog_min_dbh_cm",
                "road_extension_m",
            )
        }
        replay_root = entry.level_path.parents[2] / "replays" / entry.level_id
        optimal_dir = replay_root / "optimal"
        with self._replay_lock(optimal_dir):
            if not self._replay_consistent(optimal_dir):
                generate_replay(entry.level_path, optimal_choices, optimal_dir)
        key = hashlib.sha256(
            json.dumps(player_choices, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        player_dir = Path.cwd() / "build" / "game_replays" / entry.level_id / key
        with self._replay_lock(player_dir):
            if not self._replay_consistent(player_dir):
                generate_replay(entry.level_path, player_choices, player_dir)
        optimal_token = secrets.token_urlsafe(16)
        player_token = secrets.token_urlsafe(16)
        self.replay_tokens[optimal_token] = optimal_dir
        self.replay_tokens[player_token] = player_dir
        optimal_meta = json.loads((optimal_dir / "replay.json").read_text(encoding="utf-8"))
        player_meta = json.loads((player_dir / "replay.json").read_text(encoding="utf-8"))
        return {
            "level_id": entry.level_id,
            "optimal_url": f"/api/game/replay-assets/{optimal_token}/viewer.html",
            "player_url": f"/api/game/replay-assets/{player_token}/viewer.html",
            "optimal_duration_s": optimal_meta["duration_s"],
            "player_duration_s": player_meta["duration_s"],
            "optimal_choices": optimal_choices,
            "player_choices": player_choices,
        }

    def _replay_lock(self, directory: Path) -> threading.Lock:
        with self.replay_locks_guard:
            return self.replay_locks.setdefault(directory.resolve(), threading.Lock())

    @staticmethod
    def _replay_consistent(directory: Path) -> bool:
        try:
            meta = json.loads((directory / "replay.json").read_text(encoding="utf-8"))
            events = json.loads((directory / "system_events.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not (directory / "scene.gltf").is_file() or not (directory / "viewer.html").is_file():
            return False
        if meta.get("path_mode") != "swath":
            return False
        if meta.get("generator_version") != "fhops.game.replay.swath.v1":
            return False
        return math.isclose(
            float(meta.get("duration_s", -1.0)),
            float(events.get("duration_s", -2.0)),
            rel_tol=1e-6,
            abs_tol=0.01,
        )

    def replay_asset(self, token: str, filename: str) -> Path:
        """Resolve a token-scoped replay asset file."""
        try:
            root = self.replay_tokens[token]
        except KeyError as exc:
            raise KeyError("Unknown replay token.") from exc
        if Path(filename).name != filename:
            raise ValueError("Invalid replay asset name.")
        path = (root / filename).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise FileNotFoundError(filename)
        return path

    def _entry(self, level_id: str) -> _StandEntry:
        try:
            return self.entries[level_id]
        except KeyError as exc:
            raise KeyError(f"Unknown level_id={level_id}") from exc

    @staticmethod
    def _contractor(entry: _StandEntry, contractor_id: str | None) -> dict[str, Any]:
        contractors = entry.level.get("contractors", [])
        if not contractors:
            raise ValueError("Level has no contractor quotes.")
        target = contractor_id or contractors[0]["id"]
        for item in contractors:
            if item["id"] == target:
                return dict(item)
        raise ValueError(f"Unknown contractor_id={target!r}")

    @staticmethod
    def _contractor_adjustment(contractor: dict[str, Any], result: dict[str, Any]) -> float:
        machine_cost = float(result.get("machine_cost", 0.0))
        rate_multiplier = float(contractor.get("rate_multiplier", 1.0))
        mobilisation_adjustment = float(contractor.get("mobilisation_adjustment", 0.0))
        return -(machine_cost * (rate_multiplier - 1.0)) - mobilisation_adjustment

    @staticmethod
    def _consultant_fees(entry: _StandEntry, consultant_ids: list[str]) -> float:
        by_id = {str(item["id"]): item for item in entry.level.get("consultants", [])}
        return sum(float(by_id[item]["fee"]) for item in consultant_ids if item in by_id)

    @staticmethod
    def _tip_text(entry: _StandEntry, consultant: dict[str, Any]) -> list[str]:
        best = entry.precompute["bounds"]["best_choices"]
        labels = {
            "care_level": "careful logging",
            "skidder_count": "skidder count",
            "log_length_m": "log length",
            "sawlog_min_dbh_cm": "sawlog minimum DBH",
            "road_extension_m": "road extension",
        }
        return [
            f"{consultant['name']}: {labels[parameter]} {best[parameter]}"
            for parameter in consultant.get("parameters", [])
            if parameter in best
        ]

    def _adjusted_bounds(self, entry: _StandEntry) -> dict[str, float]:
        contractors = entry.level.get("contractors", [])
        nets = []
        for variant in entry.precompute["variants"]:
            for contractor in contractors:
                nets.append(
                    float(variant["net_profit"])
                    + self._contractor_adjustment(contractor, variant["result"])
                )
        if not nets:
            return {"best_net_profit": 0.0, "worst_net_profit": 0.0}
        return {"best_net_profit": max(nets), "worst_net_profit": min(nets)}

    @staticmethod
    def _find_variant(entry: _StandEntry, choices: GameChoicesPayload) -> dict[str, Any]:
        for record in entry.precompute["variants"]:
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
        return service.public_levels()

    @router.get("/levels/{level_id}/boundary")
    def boundary(level_id: str) -> dict[str, Any]:
        try:
            return service.boundary(level_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/sessions")
    def create_session(request: GameSessionCreate | None = None) -> dict[str, Any]:
        try:
            return service.create_session(request.session_id if request else None)
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

    @router.post("/sessions/{session_id}/teams/{team_code}/replay/{level_id}")
    def replay(session_id: str, team_code: str, level_id: str) -> dict[str, Any]:
        try:
            return service.replay(session_id, team_code, level_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (GameStateError, ValueError, FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/replay-jobs/{job_id}")
    def replay_status(job_id: str) -> dict[str, Any]:
        try:
            return service.replay_status(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/replay-assets/{token}/{filename}")
    def replay_asset(token: str, filename: str):
        from fastapi.responses import FileResponse

        try:
            return FileResponse(service.replay_asset(token, filename))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/sessions/{session_id}/teams/{team_code}/debrief/{level_id}")
    def debrief(session_id: str, team_code: str, level_id: str) -> dict[str, Any]:
        try:
            return service.debrief(session_id, team_code, level_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (GameStateError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/sessions/{session_id}/teams/{team_code}/chat")
    def chat(session_id: str, team_code: str, request: ChatRequest) -> dict[str, Any]:
        try:
            return service.chat(session_id, team_code, request.message)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (GameStateError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/sessions/{session_id}/teams/{team_code}/consult")
    def consult(session_id: str, team_code: str, request: ConsultRequest) -> dict[str, Any]:
        try:
            return service.consult(session_id, team_code, request.consultant_ids)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (GameStateError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
