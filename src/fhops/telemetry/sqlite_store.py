"""SQLite-backed storage helpers for telemetry runs, KPIs, and tuner summaries."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

__all__ = ["persist_run", "persist_tuner_summary"]


_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    schema_version TEXT,
    solver TEXT,
    scenario TEXT,
    scenario_path TEXT,
    seed INTEGER,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    duration_seconds REAL,
    config_json TEXT,
    context_json TEXT,
    extra_json TEXT,
    artifacts_json TEXT,
    tuner_meta_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS run_metrics (
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL,
    value_text TEXT,
    PRIMARY KEY (run_id, name),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS run_kpis (
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL,
    value_text TEXT,
    PRIMARY KEY (run_id, name),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tuner_summaries (
    summary_id TEXT PRIMARY KEY,
    schema_version TEXT,
    algorithm TEXT,
    scenarios_evaluated INTEGER,
    configurations INTEGER,
    scenario_best_json TEXT,
    created_at TEXT
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    if "tuner_meta_json" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN tuner_meta_json TEXT")


def _json_dumps(payload: Mapping[str, Any] | None) -> str | None:
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _prepare_metric(value: Any) -> tuple[float | None, str | None]:
    if isinstance(value, bool):
        return (1.0 if value else 0.0), None
    if isinstance(value, int | float):
        return float(value), None
    return None, json.dumps(value, ensure_ascii=False)


def persist_run(
    sqlite_path: str | Path,
    record: Mapping[str, Any],
    metrics: Mapping[str, Any] | None,
    kpis: Mapping[str, Any] | None,
) -> None:
    """Append a run record to the SQLite telemetry store."""

    path = Path(sqlite_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    try:
        _ensure_schema(conn)
        run_id = record["run_id"]
        config_json = _json_dumps(record.get("config"))
        context_json = _json_dumps(record.get("context"))
        extra_json = _json_dumps(record.get("extra"))
        artifacts_json = (
            json.dumps(record.get("artifacts", []), ensure_ascii=False)
            if record.get("artifacts")
            else None
        )
        tuner_meta_json = _json_dumps(record.get("tuner_meta"))

        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id,
                    schema_version,
                    solver,
                    scenario,
                    scenario_path,
                    seed,
                    status,
                    started_at,
                    finished_at,
                    duration_seconds,
                    config_json,
                    context_json,
                    extra_json,
                    artifacts_json,
                    tuner_meta_json,
                    error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    record.get("schema_version"),
                    record.get("solver"),
                    record.get("scenario"),
                    record.get("scenario_path"),
                    record.get("seed"),
                    record.get("status"),
                    record.get("started_at"),
                    record.get("finished_at"),
                    record.get("duration_seconds"),
                    config_json,
                    context_json,
                    extra_json,
                    artifacts_json,
                    tuner_meta_json,
                    record.get("error"),
                ),
            )

            conn.execute("DELETE FROM run_metrics WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM run_kpis WHERE run_id = ?", (run_id,))

            if metrics:
                rows = []
                for name, value in metrics.items():
                    real_value, text_value = _prepare_metric(value)
                    rows.append((run_id, str(name), real_value, text_value))
                conn.executemany(
                    "INSERT INTO run_metrics (run_id, name, value, value_text) VALUES (?, ?, ?, ?)",
                    rows,
                )

            if kpis:
                rows = []
                for name, value in kpis.items():
                    real_value, text_value = _prepare_metric(value)
                    rows.append((run_id, str(name), real_value, text_value))
                conn.executemany(
                    "INSERT INTO run_kpis (run_id, name, value, value_text) VALUES (?, ?, ?, ?)",
                    rows,
                )
    finally:
        conn.close()


def persist_tuner_summary(
    sqlite_path: str | Path,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist a tuner summary record to SQLite and return the enriched payload."""

    path = Path(sqlite_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(record)
    summary_id = payload.setdefault("summary_id", uuid4().hex)
    payload.setdefault("created_at", datetime.now(UTC).isoformat(timespec="seconds"))

    scenario_best = payload.get("scenario_best") or {}
    scenario_best_json = json.dumps(scenario_best, ensure_ascii=False, sort_keys=True)

    conn = sqlite3.connect(path)
    try:
        _ensure_schema(conn)
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tuner_summaries (
                    summary_id,
                    schema_version,
                    algorithm,
                    scenarios_evaluated,
                    configurations,
                    scenario_best_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_id,
                    payload.get("schema_version"),
                    payload.get("algorithm"),
                    payload.get("scenarios_evaluated"),
                    payload.get("configurations"),
                    scenario_best_json,
                    payload.get("created_at"),
                ),
            )
    finally:
        conn.close()

    return payload
