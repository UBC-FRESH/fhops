"""Context manager for capturing solver run telemetry."""

from __future__ import annotations

import time
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .jsonl import append_jsonl
from .sqlite_store import persist_run


def _iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class RunTelemetryLogger(AbstractContextManager["RunTelemetryLogger"]):
    """Record high-level telemetry for a solver run.

    Parameters
    ----------
    log_path:
        JSONL path where run records are appended.
    solver:
        Solver identifier (e.g., ``"sa"``, ``"ils"``).
    scenario:
        Human-readable scenario name.
    scenario_path:
        Optional filesystem path to the scenario YAML.
    seed:
        RNG seed (if applicable).
    config:
        Dictionary capturing solver configuration (iterations, operator weights, etc.).
    context:
        Additional metadata contextualising the run (source command, presets, multi-start id).
    step_interval:
        Step logging cadence. ``None`` or ``<= 0`` disables step logging.
    """

    log_path: Path
    solver: str
    scenario: str | None = None
    scenario_path: str | None = None
    seed: int | None = None
    config: Mapping[str, Any] | None = None
    context: Mapping[str, Any] | None = None
    step_interval: int | None = 100
    schema_version: str = "1.1"
    sqlite_path: Path | None = None
    run_id: str = field(default_factory=lambda: uuid4().hex, init=False)
    _start_time: float = field(default=0.0, init=False)
    _start_timestamp: str | None = field(default=None, init=False)
    _closed: bool = field(default=False, init=False)
    _steps_path: Path | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.log_path = Path(self.log_path)
        if self.sqlite_path is None and self.log_path:
            self.sqlite_path = self.log_path.with_suffix(".sqlite")
        if self.step_interval and self.step_interval > 0:
            self._steps_path = self.log_path.parent / "steps" / f"{self.run_id}.jsonl"

    def __enter__(self) -> RunTelemetryLogger:
        self._start_time = time.perf_counter()
        self._start_timestamp = _iso_now()
        if self._steps_path:
            self._steps_path.parent.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type:
            self._close(
                status="error",
                metrics=None,
                extra=None,
                error=repr(exc),
                artifacts=None,
                kpis=None,
                tuner_meta=None,
            )
            return False
        self._close(
            status="ok",
            metrics=None,
            extra=None,
            error=None,
            artifacts=None,
            kpis=None,
            tuner_meta=None,
        )
        return False

    def log_step(
        self,
        *,
        step: int,
        objective: float,
        best_objective: float,
        temperature: float | None,
        acceptance_rate: float | None,
        proposals: int,
        accepted_moves: int,
    ) -> None:
        """Persist a step-level snapshot when step logging is enabled."""
        if not self._steps_path:
            return
        record = {
            "record_type": "step",
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "timestamp": _iso_now(),
            "step": step,
            "objective": objective,
            "best_objective": best_objective,
            "temperature": temperature,
            "acceptance_rate": acceptance_rate,
            "proposals": proposals,
            "accepted_moves": accepted_moves,
        }
        append_jsonl(self._steps_path, record)

    def elapsed(self) -> float:
        """Return the elapsed wall-clock seconds since the run started."""
        return time.perf_counter() - self._start_time

    @property
    def steps_path(self) -> Path | None:
        """Return the step-log path if step logging is enabled."""
        return self._steps_path

    def finalize(
        self,
        *,
        status: str = "ok",
        metrics: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
        error: str | None = None,
        artifacts: list[str] | None = None,
        kpis: Mapping[str, Any] | None = None,
        tuner_meta: Mapping[str, Any] | None = None,
    ) -> None:
        """Write the terminal run record."""
        self._close(
            status=status,
            metrics=metrics,
            extra=extra,
            error=error,
            artifacts=artifacts,
            kpis=kpis,
            tuner_meta=tuner_meta,
        )

    def _close(
        self,
        *,
        status: str,
        metrics: Mapping[str, Any] | None,
        extra: Mapping[str, Any] | None,
        error: str | None,
        artifacts: list[str] | None,
        kpis: Mapping[str, Any] | None,
        tuner_meta: Mapping[str, Any] | None,
    ) -> None:
        if self._closed:
            return
        finished_at = _iso_now()
        duration = self.elapsed() if self._start_time else 0.0
        context_payload = dict(self.context or {})
        record = {
            "record_type": "run",
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "solver": self.solver,
            "scenario": self.scenario,
            "scenario_path": self.scenario_path,
            "seed": self.seed,
            "status": status,
            "metrics": dict(metrics or {}),
            "config": dict(self.config or {}),
            "context": context_payload,
            "extra": dict(extra or {}),
            "artifacts": list(artifacts or []),
            "error": error,
            "started_at": self._start_timestamp,
            "finished_at": finished_at,
            "duration_seconds": round(duration, 3),
            "tuner_meta": dict(tuner_meta or {}),
        }
        # Promote common context fields for backwards compatibility with legacy tooling.
        for promoted_key in ("source", "command", "profile", "profile_version", "tier"):
            if promoted_key in context_payload and promoted_key not in record:
                record[promoted_key] = context_payload[promoted_key]
        if metrics:
            record["metrics"] = dict(metrics)
        else:
            record["metrics"] = {}
        if kpis:
            record["kpis"] = dict(kpis)
        else:
            record["kpis"] = {}
        extra_payload = record["extra"]
        if isinstance(extra_payload, dict):
            if "export" in extra_payload and "export" not in record:
                record["export"] = extra_payload["export"]
            if "scenario_features" in extra_payload and "scenario_features" not in record:
                record["scenario_features"] = extra_payload["scenario_features"]
            if "export_metrics" in extra_payload and "export_metrics" not in record:
                record["export_metrics"] = extra_payload["export_metrics"]
        append_jsonl(self.log_path, record)
        if self.sqlite_path:
            persist_run(
                self.sqlite_path,
                record=record,
                metrics=record["metrics"],
                kpis=record["kpis"],
            )
        self._closed = True


__all__ = ["RunTelemetryLogger"]
