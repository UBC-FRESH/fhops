"""Schedule-bound road/culvert exposure tests (P15.4)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from fhops.scenario.hydrology_exposure import (
    HYDROLOGY_EXPOSURE_SCHEMA,
    FemicHydrologyExposureError,
    load_hydrology_exposure,
    schedule_sha256,
    validate_hydrology_exposure,
)


def _schedule(tmp_path: Path) -> Path:
    path = tmp_path / "assignments.csv"
    path.write_text(
        "machine_id,block_id,day,shift_id\nM1,B01,1,S1\nM2,B02,1,S1\n",
        encoding="utf-8",
    )
    return path


def _payload(schedule: Path) -> dict[str, object]:
    return {
        "schema_version": HYDROLOGY_EXPOSURE_SCHEMA,
        "exposure_id": "exposure-fixture-001",
        "generated_utc": "2026-10-27T00:00:00+00:00",
        "source_id": "synthetic-road-culvert-fixture",
        "review_status": "reviewed",
        "reviewer_id": "reviewer-1",
        "schedule_sha256": hashlib.sha256(schedule.read_bytes()).hexdigest(),
        "watershed_ids": ["watershed-1", "watershed-2"],
        "periods": [0, 1],
        "rows": [
            {
                "watershed_id": "watershed-1",
                "period": 0,
                "road_built_km": 0.0,
                "road_used_km": 1.0,
                "road_decommissioned_km": 0.0,
                "culvert_count": 3,
                "culvert_exposed_count": 1,
            },
            {
                "watershed_id": "watershed-1",
                "period": 1,
                "road_built_km": 0.5,
                "road_used_km": 1.5,
                "road_decommissioned_km": 0.0,
                "culvert_count": 3,
                "culvert_exposed_count": 2,
            },
            {
                "watershed_id": "watershed-2",
                "period": 0,
                "road_built_km": 0.0,
                "road_used_km": 0.5,
                "road_decommissioned_km": 0.0,
                "culvert_count": 1,
                "culvert_exposed_count": 0,
            },
            {
                "watershed_id": "watershed-2",
                "period": 1,
                "road_built_km": 0.0,
                "road_used_km": 0.75,
                "road_decommissioned_km": 0.25,
                "culvert_count": 1,
                "culvert_exposed_count": 1,
            },
        ],
        "caveats": ["Synthetic exposure fixture only."],
    }


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_load_exposure_and_features(tmp_path: Path) -> None:
    schedule = _schedule(tmp_path)
    exposure = load_hydrology_exposure(
        _write(tmp_path / "exposure.json", _payload(schedule)), schedule_path=schedule
    )

    assert exposure.exposure_id == "exposure-fixture-001"
    assert exposure.review_status == "reviewed"
    assert exposure.schedule_sha256 == schedule_sha256(schedule)
    assert exposure.periods == (0, 1)
    assert len(exposure.rows) == 4
    raw = exposure.features_for("watershed-1", 1)
    assert raw["road_used_km"] == pytest.approx(1.5)
    assert raw["culvert_exposed_count"] == pytest.approx(2.0)
    assert "road_used_density_km_per_km2" not in raw
    density = exposure.features_for("watershed-1", 1, watershed_area_ha=150.0)
    assert density["road_used_density_km_per_km2"] == pytest.approx(1.0)
    assert density["culvert_exposure_per_km2"] == pytest.approx(2.0 / 1.5)

    report = validate_hydrology_exposure(Path(exposure.path), schedule_path=schedule)
    assert report.is_valid is True
    assert report.row_count == 4
    assert report.watershed_count == 2
    assert report.period_count == 2


def test_schedule_mismatch_is_rejected(tmp_path: Path) -> None:
    schedule = _schedule(tmp_path)
    other = tmp_path / "other.csv"
    other.write_text("machine_id,block_id,day,shift_id\nM1,B01,2,S1\n", encoding="utf-8")
    path = _write(tmp_path / "exposure.json", _payload(schedule))

    with pytest.raises(FemicHydrologyExposureError, match="schedule hash"):
        load_hydrology_exposure(path, schedule_path=other)


def test_missing_duplicate_and_invalid_rows_fail(tmp_path: Path) -> None:
    schedule = _schedule(tmp_path)
    payload = _payload(schedule)
    rows = payload["rows"]
    assert isinstance(rows, list)
    payload["rows"] = rows[:-1]
    with pytest.raises(FemicHydrologyExposureError, match="missing 1 declared row"):
        load_hydrology_exposure(_write(tmp_path / "missing.json", payload))

    payload = _payload(schedule)
    rows = payload["rows"]
    assert isinstance(rows, list)
    payload["rows"] = [*rows, rows[0]]
    with pytest.raises(FemicHydrologyExposureError, match="Duplicate exposure row"):
        load_hydrology_exposure(_write(tmp_path / "duplicate.json", payload))

    payload = _payload(schedule)
    rows = payload["rows"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    first["road_used_km"] = -1.0
    with pytest.raises(FemicHydrologyExposureError, match="finite non-negative"):
        load_hydrology_exposure(_write(tmp_path / "negative.json", payload))

    payload = _payload(schedule)
    rows = payload["rows"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    first["road_used_km"] = math.inf
    with pytest.raises(FemicHydrologyExposureError, match="finite non-negative"):
        load_hydrology_exposure(_write(tmp_path / "infinite.json", payload))

    payload = _payload(schedule)
    rows = payload["rows"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    first["culvert_count"] = 1.5
    with pytest.raises(FemicHydrologyExposureError, match="non-negative integer"):
        load_hydrology_exposure(_write(tmp_path / "count.json", payload))


def test_review_and_schedule_fields_are_required(tmp_path: Path) -> None:
    schedule = _schedule(tmp_path)
    payload = _payload(schedule)
    payload["reviewer_id"] = None
    with pytest.raises(FemicHydrologyExposureError, match="reviewer_id"):
        load_hydrology_exposure(_write(tmp_path / "reviewer.json", payload))

    payload = _payload(schedule)
    payload["schedule_sha256"] = "not-a-digest"
    with pytest.raises(FemicHydrologyExposureError, match="64-character hex"):
        load_hydrology_exposure(_write(tmp_path / "schedule.json", payload))

    payload = _payload(schedule)
    payload["schema_version"] = "ws4.hydrology.exposure.v2"
    with pytest.raises(FemicHydrologyExposureError, match="Unsupported exposure schema"):
        load_hydrology_exposure(_write(tmp_path / "schema.json", payload))


def test_unknown_grid_ids_and_bad_area_fail(tmp_path: Path) -> None:
    schedule = _schedule(tmp_path)
    payload = _payload(schedule)
    rows = payload["rows"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    first["watershed_id"] = "watershed-99"
    with pytest.raises(FemicHydrologyExposureError, match="undeclared watershed"):
        load_hydrology_exposure(_write(tmp_path / "watershed.json", payload))

    payload = _payload(schedule)
    rows = payload["rows"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    first["period"] = 99
    with pytest.raises(FemicHydrologyExposureError, match="undeclared period"):
        load_hydrology_exposure(_write(tmp_path / "period.json", payload))

    exposure = load_hydrology_exposure(_write(tmp_path / "valid.json", _payload(schedule)))
    with pytest.raises(FemicHydrologyExposureError, match="watershed_area_ha"):
        exposure.features_for("watershed-1", 0, watershed_area_ha=0)
    with pytest.raises(FemicHydrologyExposureError, match="no row"):
        exposure.features_for("watershed-99", 0)


def test_validation_report_reports_errors(tmp_path: Path) -> None:
    schedule = _schedule(tmp_path)
    payload = _payload(schedule)
    payload["periods"] = [0]
    path = _write(tmp_path / "bad.json", payload)

    report = validate_hydrology_exposure(path, schedule_path=schedule)
    assert report.is_valid is False
    assert report.errors
    assert report.schedule_sha256 == hashlib.sha256(schedule.read_bytes()).hexdigest()
