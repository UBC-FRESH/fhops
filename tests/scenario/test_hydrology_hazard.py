"""Operational hazard-window contract tests (P16.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.hydrology_hazard import (
    HYDROLOGY_HAZARD_SCHEMA,
    FemicHydrologyHazardError,
    load_hydrology_hazard,
    validate_hydrology_hazard,
)

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "hazard" / "valid.json"


def _payload() -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_load_and_lookup_severity() -> None:
    hazard = load_hydrology_hazard(FIXTURE)

    assert hazard.hazard_id == "hazard-fixture-001"
    assert hazard.review_status == "reviewed"
    assert len(hazard.windows) == 4
    assert hazard.severity_for("watershed-1", 1) == "watch"
    assert hazard.severity_for("watershed-1", 3) == "warning"
    assert hazard.severity_for("watershed-1", 5) == "closure"
    assert hazard.severity_for("watershed-2", 2) == "warning"
    assert hazard.severity_for("watershed-1", 9) is None
    assert hazard.to_dict()["schema_version"] == HYDROLOGY_HAZARD_SCHEMA


def test_validation_rejects_bad_schema_and_reviewer(tmp_path: Path) -> None:
    payload = _payload()
    payload["schema_version"] = "fhops.hydrology.hazard.v2"
    report = validate_hydrology_hazard(_write(tmp_path / "schema.json", payload))
    assert report.is_valid is False
    assert any("Unsupported hazard schema" in error for error in report.errors)

    payload = _payload()
    payload["reviewer_id"] = None
    report = validate_hydrology_hazard(_write(tmp_path / "reviewer.json", payload))
    assert report.is_valid is False
    assert any("reviewer_id" in error for error in report.errors)


def test_validation_rejects_bad_days_and_empty_lists(tmp_path: Path) -> None:
    payload = _payload()
    windows = payload["windows"]
    assert isinstance(windows, list)
    first = windows[0]
    assert isinstance(first, dict)
    first["start_day"] = 4
    first["end_day"] = 2
    report = validate_hydrology_hazard(_write(tmp_path / "days.json", payload))
    assert any("start_day must be <= end_day" in error for error in report.errors)

    payload = _payload()
    payload["windows"] = []
    report = validate_hydrology_hazard(_write(tmp_path / "empty.json", payload))
    assert any("windows must be a non-empty list" in error for error in report.errors)

    payload = _payload()
    payload["caveats"] = []
    report = validate_hydrology_hazard(_write(tmp_path / "caveats.json", payload))
    assert any("caveats must not be empty" in error for error in report.errors)


def test_duplicate_and_overlap_rules(tmp_path: Path) -> None:
    payload = _payload()
    windows = payload["windows"]
    assert isinstance(windows, list)
    payload["windows"] = [*windows, windows[0]]
    report = validate_hydrology_hazard(_write(tmp_path / "duplicate.json", payload))
    assert any("Duplicate hazard window" in error for error in report.errors)

    payload = _payload()
    windows = payload["windows"]
    assert isinstance(windows, list)
    first = windows[0]
    assert isinstance(first, dict)
    windows.append(
        {
            "watershed_id": "watershed-1",
            "start_day": 2,
            "end_day": 3,
            "severity": "watch",
            "return_period_years": 2.0,
            "source_id": "synthetic",
            "notes": "",
        }
    )
    report = validate_hydrology_hazard(_write(tmp_path / "overlap-same.json", payload))
    assert any(
        "Overlapping hazard windows of the same severity" in error for error in report.errors
    )

    payload = _payload()
    windows = payload["windows"]
    assert isinstance(windows, list)
    windows.append(
        {
            "watershed_id": "watershed-1",
            "start_day": 2,
            "end_day": 3,
            "severity": "closure",
            "return_period_years": 10.0,
            "source_id": "synthetic",
            "notes": "",
        }
    )
    report = validate_hydrology_hazard(_write(tmp_path / "overlap-mixed.json", payload))
    assert report.is_valid is True
    assert any("highest severity applies" in warning for warning in report.warnings)


def test_load_raises_on_invalid_table(tmp_path: Path) -> None:
    payload = _payload()
    payload["source_id"] = ""
    with pytest.raises(FemicHydrologyHazardError, match="source_id"):
        load_hydrology_hazard(_write(tmp_path / "bad.json", payload))


def test_cli_validate() -> None:
    result = runner.invoke(
        app,
        ["scenario", "hydrology", "hazard", "validate", str(FIXTURE)],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["is_valid"] is True
    assert payload["window_count"] == 4
