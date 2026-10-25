"""Tests for run discovery and the run manifest."""

from __future__ import annotations

from pathlib import Path

from fhops.web.discovery import (
    build_run_manifest,
    classify_run,
    discover_runs,
    load_run_manifest,
)


def _write(run_dir: Path, *names: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (run_dir / name).write_text("value\n", encoding="utf-8")


def test_classify_operational() -> None:
    domain, run_type, warnings = classify_run(
        {"assignments": "sa_solution.csv", "telemetry": "telemetry.jsonl"}
    )
    assert domain == "operational"
    assert run_type == "solve"
    assert warnings == []


def test_classify_hauling_plan_schedule_and_solve() -> None:
    assert classify_run({"haul_flows": "haul_flows.csv"})[:2] == ("hauling", "haul_plan")
    assert classify_run({"haul_schedule": "haul_schedule.csv"})[:2] == (
        "hauling",
        "haul_schedule",
    )
    assert classify_run({"haul_flows": "haul_flows.csv", "haul_schedule": "haul_schedule.csv"})[
        :2
    ] == ("hauling", "haul_solve")


def test_classify_tactical() -> None:
    domain, run_type, warnings = classify_run(
        {"harvest_decisions": "harvest_decisions.csv", "production": "production.csv"}
    )
    assert domain == "tactical_operational"
    assert run_type == "tactical_operational"
    assert warnings == []


def test_ambiguous_domains_are_warned() -> None:
    domain, _run_type, warnings = classify_run(
        {"haul_flows": "haul_flows.csv", "harvest_decisions": "harvest_decisions.csv"}
    )
    assert domain == "hauling"
    assert any("multiple domains" in warning for warning in warnings)


def test_manifest_round_trip(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    _write(run_dir, "assignments.csv", "telemetry.jsonl")
    payload = build_run_manifest(
        run_dir,
        command="fhops solve-heur scenario.yaml",
        scenario="scenario.yaml",
        solver="sa",
        seed=42,
        status="ok",
    )
    assert payload["domain"] == "operational"
    assert payload["run_type"] == "solve"
    assert payload["files"]["assignments"] == "assignments.csv"
    stored = load_run_manifest(run_dir)
    assert stored is not None
    assert stored["run_id"] == "run-a"
    assert stored["solver"] == "sa"


def test_discover_nested_runs(tmp_path: Path) -> None:
    _write(tmp_path / "run-a", "haul_flows.csv")
    _write(tmp_path / "nested" / "run-b", "harvest_decisions.csv")
    records = discover_runs([tmp_path])
    assert {record.run_id for record in records} == {"run-a", "nested-run-b"}
    domains = {record.run_id: record.domain for record in records}
    assert domains["run-a"] == "hauling"
    assert domains["nested-run-b"] == "tactical_operational"


def test_invalid_manifest_is_reported(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(run_dir, "haul_flows.csv")
    (run_dir / "run.json").write_text("{not json", encoding="utf-8")
    records = discover_runs([tmp_path])
    assert len(records) == 1
    assert any("invalid run.json" in warning for warning in records[0].warnings)
