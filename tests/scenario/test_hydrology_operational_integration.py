"""End-to-end flood-aware operational constraint tests (P16.5)."""

from __future__ import annotations

import json
from pathlib import Path

from test_hydrology_screen import _mapping, _scenario
from typer.testing import CliRunner

from fhops.cli.main import app

runner = CliRunner()
HAZARD = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "hazard" / "valid.json"
ASSETS = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "assets" / "valid.json"


def _schedule(tmp_path: Path) -> Path:
    path = tmp_path / "assignments.csv"
    path.write_text(
        "machine_id,block_id,day,shift_id\n"
        "M1,T6_19212607,1,S1\n"
        "M1,T6_23339461,3,S1\n"
        "M1,T6_23339462,5,S1\n",
        encoding="utf-8",
    )
    return path


def test_end_to_end_operational_constraint_path(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    schedule = _schedule(tmp_path)
    out = tmp_path / "constraint-check"

    hazard = runner.invoke(
        app,
        ["scenario", "hydrology", "hazard", "validate", str(HAZARD)],
        prog_name="fhops",
    )
    assert hazard.exit_code == 0, hazard.output
    assert json.loads(hazard.output)["window_count"] == 4

    assets = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "assets",
            "validate",
            str(ASSETS),
            "--scenario",
            str(scenario),
            "--mapping",
            str(mapping),
        ],
        prog_name="fhops",
    )
    assert assets.exit_code == 0, assets.output
    assert json.loads(assets.output)["asset_count"] == 2

    checked = runner.invoke(
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
            "--no-fail-on-closure",
            "--out",
            str(out),
        ],
        prog_name="fhops",
    )
    assert checked.exit_code == 0, checked.output
    payload = json.loads(checked.output)
    assert payload["failed"] is False
    assert payload["coverage"]["watch_events"] == 1
    assert payload["coverage"]["warning_events"] == 1
    assert payload["coverage"]["closure_events"] == 1
    assert (out / "hydrology_constraint_events.csv").is_file()
    assert (out / "hydrology_constraint_check.json").is_file()


def test_end_to_end_closure_fails_by_default(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    schedule = _schedule(tmp_path)
    result = runner.invoke(
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
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["failed"] is True
    assert payload["failure_reasons"]


def test_end_to_end_rejects_tampered_hazard(tmp_path: Path) -> None:
    hazard = tmp_path / "hazard.json"
    hazard.write_text(
        HAZARD.read_text(encoding="utf-8").replace('"closure"', '"closed"'), encoding="utf-8"
    )
    result = runner.invoke(
        app,
        ["scenario", "hydrology", "hazard", "validate", str(hazard)],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "unsupported severity" in result.output


def test_end_to_end_rejects_unknown_asset(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    assets = tmp_path / "assets.json"
    assets.write_text(ASSETS.read_text(encoding="utf-8").replace('"R1"', '"R99"'), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "assets",
            "validate",
            str(assets),
            "--scenario",
            str(scenario),
            "--mapping",
            str(mapping),
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "unknown road job" in result.output
