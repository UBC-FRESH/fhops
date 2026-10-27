"""Flood-aware operational constraint-check tests (P16.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_hydrology_screen import _mapping, _scenario
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.hydrology_constraint_check import (
    FemicHydrologyConstraintError,
    check_fhops_hydrology_constraints,
    write_hydrology_constraint_check,
)

runner = CliRunner()
HAZARD = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "hazard" / "valid.json"
ASSETS = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "assets" / "valid.json"


def _schedule(tmp_path: Path, *, days: tuple[int, ...] = (1, 3, 5)) -> Path:
    blocks = {
        1: "T6_19212607",
        3: "T6_23339461",
        5: "T6_23339462",
    }
    path = tmp_path / "assignments.csv"
    rows = ["machine_id,block_id,day,shift_id"]
    rows.extend(f"M1,{blocks[day]},{day},S1" for day in days)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    return scenario, mapping


def test_check_reports_watch_warning_and_closure(tmp_path: Path) -> None:
    scenario, mapping = _fixture(tmp_path)
    schedule = _schedule(tmp_path)

    result = check_fhops_hydrology_constraints(
        scenario,
        mapping,
        schedule,
        HAZARD,
        assets_path=ASSETS,
        fail_on_closure=False,
        generated_utc="2026-10-27T00:00:00+00:00",
    )

    assert result.failed is False
    assert [event.severity for event in result.events] == ["watch", "warning", "closure"]
    assert all(event.asset_ids == ("R1", "C1") for event in result.events)
    assert result.coverage["watch_events"] == 1
    assert result.coverage["warning_events"] == 1
    assert result.coverage["closure_events"] == 1
    assert result.schedule_sha256

    paths = write_hydrology_constraint_check(result, tmp_path / "check")
    assert paths["events"].is_file()
    assert paths["manifest"].is_file()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "fhops.hydrology.constraint_check.v1"
    assert manifest["event_count"] == 3


def test_closure_fails_by_default_and_warning_is_policy(tmp_path: Path) -> None:
    scenario, mapping = _fixture(tmp_path)
    schedule = _schedule(tmp_path)

    closure = check_fhops_hydrology_constraints(scenario, mapping, schedule, HAZARD)
    assert closure.failed is True
    assert any("Closure-window" in reason for reason in closure.failure_reasons)

    warning = check_fhops_hydrology_constraints(
        scenario,
        mapping,
        schedule,
        HAZARD,
        fail_on_closure=False,
        fail_on_warning=True,
    )
    assert warning.failed is True
    assert any("Warning-window" in reason for reason in warning.failure_reasons)

    watch = check_fhops_hydrology_constraints(
        scenario,
        mapping,
        _schedule(tmp_path, days=(1,)),
        HAZARD,
    )
    assert watch.failed is False
    assert watch.events[0].severity == "watch"


def test_missing_mapping_block_refuses(tmp_path: Path) -> None:
    scenario, mapping = _fixture(tmp_path)
    schedule = tmp_path / "bad.csv"
    schedule.write_text("machine_id,block_id,day,shift_id\nM1,B99,1,S1\n", encoding="utf-8")

    with pytest.raises(FemicHydrologyConstraintError, match="no hydrology mapping"):
        check_fhops_hydrology_constraints(scenario, mapping, schedule, HAZARD)


def test_cli_constraint_check_writes_and_exits(tmp_path: Path) -> None:
    scenario, mapping = _fixture(tmp_path)
    schedule = _schedule(tmp_path)
    out = tmp_path / "cli-check"

    failed = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "constraint-check",
            str(scenario),
            str(mapping),
            str(schedule),
            str(HAZARD),
            "--assets",
            str(ASSETS),
            "--out",
            str(out),
        ],
        prog_name="fhops",
    )
    assert failed.exit_code == 1
    payload = json.loads(failed.output)
    assert payload["failed"] is True
    assert (out / "hydrology_constraint_events.csv").is_file()
    assert (out / "hydrology_constraint_check.json").is_file()

    allowed = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "constraint-check",
            str(scenario),
            str(mapping),
            str(schedule),
            str(HAZARD),
            "--no-fail-on-closure",
        ],
        prog_name="fhops",
    )
    assert allowed.exit_code == 0, allowed.output
    assert json.loads(allowed.output)["failed"] is False
