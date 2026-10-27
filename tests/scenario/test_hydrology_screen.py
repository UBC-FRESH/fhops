"""One-schedule hydrology screening tests (P15.5)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from test_hydrology_mapping import (
    SCENARIO,
    _rows,
    _scenario,
    _write_crosswalk,
    _write_metadata,
)
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.hydrology import FemicHydrologyReadiness
from fhops.scenario.hydrology_mapping import (
    FemicHydrologyMappingError,
    load_hydrology_mapping,
    map_femic_hydrology_to_scenario,
    write_hydrology_mapping,
)
from fhops.scenario.hydrology_registration import register_femic_hydrology_bundle
from fhops.scenario.hydrology_screen import (
    FemicHydrologyScreenError,
    enforce_hydrology_readiness,
    screen_fhops_hydrology,
    write_hydrology_screen,
)

runner = CliRunner()
BUNDLE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "response"


def _schedule(tmp_path: Path) -> Path:
    path = tmp_path / "assignments.csv"
    path.write_text(
        "machine_id,block_id,day,shift_id\nM1,T6_19212607,1,S1\nM1,T6_23339461,2,S1\n",
        encoding="utf-8",
    )
    return path


def _exposure(
    tmp_path: Path,
    schedule: Path,
    *,
    periods: tuple[int, ...] = (0, 1),
    schedule_sha256: str | None = None,
    review_status: str = "reviewed",
) -> Path:
    payload = {
        "schema_version": "ws4.hydrology.exposure.v1",
        "exposure_id": "exposure-fixture-001",
        "generated_utc": "2026-10-27T00:00:00+00:00",
        "source_id": "synthetic-road-culvert-fixture",
        "review_status": review_status,
        "reviewer_id": "reviewer-1" if review_status == "reviewed" else None,
        "schedule_sha256": schedule_sha256 or hashlib.sha256(schedule.read_bytes()).hexdigest(),
        "watershed_ids": ["watershed-1"],
        "periods": list(periods),
        "rows": [
            {
                "watershed_id": "watershed-1",
                "period": period,
                "road_built_km": 0.0,
                "road_used_km": 1.0 + period,
                "road_decommissioned_km": 0.0,
                "culvert_count": 2,
                "culvert_exposed_count": period,
            }
            for period in periods
        ],
        "caveats": ["Synthetic exposure fixture only."],
    }
    path = tmp_path / "exposure.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _mapping(tmp_path: Path, scenario: Path) -> Path:
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", _rows(scenario))
    metadata = _write_metadata(
        tmp_path / "crosswalk.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )
    mapping = map_femic_hydrology_to_scenario(
        scenario,
        BUNDLE,
        crosswalk,
        metadata_path=metadata,
        generated_utc="2026-10-27T00:00:00+00:00",
    )
    return write_hydrology_mapping(mapping, tmp_path / "mapping")["manifest"]


def _ready(status: str = "ready") -> FemicHydrologyReadiness:
    return FemicHydrologyReadiness(
        status=status,
        validation_report_id="validation-1",
        model_card_id="card-1",
        review_status="reviewed" if status == "ready" else "not_reviewed",
        full_process_pilot_ready=True,
        hydrologist_review_recorded=status == "ready",
        tail_check_failures={},
        usable_fits={},
        benchmark_cases=0,
        benchmark_passed=0,
        benchmark_failed=0,
        benchmark_not_evaluated=0,
        warnings=(),
        caveats=(),
        evidence_sha256="hydro-evidence-0000000000000000",
    )


def test_screen_schedule_produces_rows_and_exposure_features(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule)

    screen = screen_fhops_hydrology(
        scenario,
        BUNDLE,
        mapping,
        schedule,
        exposure,
        generated_utc="2026-10-27T00:00:00+00:00",
    )

    assert screen.readiness_status == "ready"
    assert screen.rows
    assert len(screen.rows) == 2
    assert screen.refusals == ()
    assert screen.rows[0]["day"] == 1
    assert screen.rows[0]["period"] == 0
    assert screen.rows[0]["scenario_name"] == "baseline"
    assert screen.rows[0]["harvest_fraction"] == pytest.approx(0.012344457180374413)
    assert screen.rows[0]["road_used_km"] == pytest.approx(1.0)
    assert screen.rows[1]["road_used_km"] == pytest.approx(2.0)
    assert screen.rows[0]["screening_peak_flow_m3s"] == pytest.approx(120.0)
    assert screen.coverage["exposure_used"] is True
    assert screen.to_dict()["exposure_sha256"]
    assert "Synthetic exposure fixture only." in screen.caveats

    paths = write_hydrology_screen(screen, tmp_path / "screen")
    assert paths["rows"].is_file()
    assert paths["manifest"].is_file()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "fhops.hydrology.screen.v1"
    assert manifest["row_count"] == 2
    assert manifest["exposure_sha256"] == screen.exposure_sha256
    assert manifest["coverage"]["exposure_used"] is True
    assert "Synthetic exposure fixture only." in manifest["caveats"]


def test_screen_selects_high_response_scenario(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    schedule = tmp_path / "assignments.csv"
    schedule.write_text(
        "machine_id,block_id,day,shift_id\nM1,T6_23339458,1,S1\n",
        encoding="utf-8",
    )
    exposure = _exposure(tmp_path, schedule)

    screen = screen_fhops_hydrology(
        scenario,
        BUNDLE,
        mapping,
        schedule,
        exposure,
        scenario_tolerance=0.3,
    )

    assert screen.rows[0]["scenario_name"] == "high"
    assert screen.rows[0]["response_ratio"] == pytest.approx(1.25)
    assert screen.rows[0]["screening_peak_flow_m3s"] == pytest.approx(150.0)


def test_screen_refuses_mapping_from_another_scenario(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    other = tmp_path / "other"
    shutil.copytree(SCENARIO.parent, other)
    register_femic_hydrology_bundle(other / "scenario.yaml", BUNDLE)
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule)

    with pytest.raises(FemicHydrologyScreenError, match="different scenario"):
        screen_fhops_hydrology(
            other / "scenario.yaml",
            BUNDLE,
            mapping,
            schedule,
            exposure,
        )


def test_mapping_loader_refuses_duplicate_rows(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    payload = json.loads(mapping.read_text(encoding="utf-8"))
    payload["rows"].append(dict(payload["rows"][0]))
    duplicate = tmp_path / "duplicate-mapping.json"
    duplicate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FemicHydrologyMappingError, match="Duplicate mapping row"):
        load_hydrology_mapping(duplicate)


def test_screen_refuses_schedule_beyond_horizon_and_unknown_blocks(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    late = tmp_path / "late.csv"
    late.write_text(
        "machine_id,block_id,day,shift_id\nM1,T6_19212607,99,S1\n",
        encoding="utf-8",
    )
    late_exposure = _exposure(tmp_path, late, periods=(0, 98))
    with pytest.raises(FemicHydrologyScreenError, match="exceeds the scenario horizon"):
        screen_fhops_hydrology(scenario, BUNDLE, mapping, late, late_exposure)

    unknown = tmp_path / "unknown.csv"
    unknown.write_text(
        "machine_id,block_id,day,shift_id\nM1,B99,1,S1\n",
        encoding="utf-8",
    )
    unknown_exposure = _exposure(tmp_path, unknown)
    with pytest.raises(FemicHydrologyScreenError, match="unknown block"):
        screen_fhops_hydrology(scenario, BUNDLE, mapping, unknown, unknown_exposure)


def test_screen_refuses_schedule_hash_mismatch(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule, schedule_sha256="b" * 64)

    with pytest.raises(FemicHydrologyScreenError, match="schedule hash"):
        screen_fhops_hydrology(scenario, BUNDLE, mapping, schedule, exposure)


def test_screen_refuses_missing_exposure_period(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule, periods=(0,))

    screen = screen_fhops_hydrology(
        scenario,
        BUNDLE,
        mapping,
        schedule,
        exposure,
        allow_refused=True,
    )
    assert any("Exposure has no declared row" in str(item["reason"]) for item in screen.refusals)


def test_screen_refuses_unmapped_block(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    crosswalk = _write_crosswalk(tmp_path / "partial.csv", [_rows(scenario)[0]])
    metadata = _write_metadata(
        tmp_path / "partial.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )
    partial = map_femic_hydrology_to_scenario(
        scenario,
        BUNDLE,
        crosswalk,
        metadata_path=metadata,
        allow_partial=True,
    )
    mapping = write_hydrology_mapping(partial, tmp_path / "partial-mapping")["manifest"]
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule)

    screen = screen_fhops_hydrology(
        scenario,
        BUNDLE,
        mapping,
        schedule,
        exposure,
        allow_refused=True,
    )
    assert any("no hydraulic mapping" in str(item["reason"]) for item in screen.refusals)


def test_readiness_policies() -> None:
    enforce_hydrology_readiness(_ready("provisional"), policy="allow_provisional")
    with pytest.raises(FemicHydrologyScreenError, match="not reviewed"):
        enforce_hydrology_readiness(_ready("provisional"), policy="require_reviewed")
    with pytest.raises(FemicHydrologyScreenError, match="not fully ready"):
        enforce_hydrology_readiness(_ready("conditionally_ready"), policy="require_ready")
    with pytest.raises(FemicHydrologyScreenError, match="Tail-check"):
        enforce_hydrology_readiness(_ready("blocked"), policy="allow_provisional")


def test_cli_screen_writes_outputs(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = _mapping(tmp_path, scenario)
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule)
    out = tmp_path / "cli-screen"

    result = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "screen",
            str(scenario),
            str(BUNDLE),
            str(mapping),
            str(schedule),
            str(exposure),
            "--out",
            str(out),
        ],
        prog_name="fhops",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["row_count"] == 2
    assert (out / "hydrology_screen.csv").is_file()
    assert (out / "hydrology_screen.json").is_file()
