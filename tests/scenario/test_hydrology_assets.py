"""Road/culvert asset evidence tests (P16.2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from test_hydrology_mapping import _rows, _scenario, _write_crosswalk, _write_metadata
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.hydrology_assets import (
    HYDROLOGY_ASSETS_SCHEMA,
    FemicHydrologyAssetError,
    load_hydrology_assets,
    map_hydrology_assets,
    validate_hydrology_assets,
)
from fhops.scenario.hydrology_mapping import (
    map_femic_hydrology_to_scenario,
    write_hydrology_mapping,
)

runner = CliRunner()
BUNDLE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "response"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "assets" / "valid.json"


def _payload() -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _mapping(tmp_path: Path) -> tuple[Path, Path]:
    scenario = _scenario(tmp_path)
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
    return scenario, write_hydrology_mapping(mapping, tmp_path / "mapping")["manifest"]


def test_load_and_validate_assets() -> None:
    assets, report = load_hydrology_assets(FIXTURE)

    assert assets.inventory_id == "assets-fixture-001"
    assert assets.review_status == "reviewed"
    assert len(assets.assets) == 2
    assert assets.assets[0].asset_type == "road"
    assert assets.assets[0].road_job_id == "R1"
    assert assets.assets[1].asset_type == "culvert"
    assert report.is_valid is True
    assert report.asset_count == 2
    assert assets.to_dict()["schema_version"] == HYDROLOGY_ASSETS_SCHEMA


def test_map_assets_to_scenario_and_mapping(tmp_path: Path) -> None:
    scenario, mapping = _mapping(tmp_path)
    result = map_hydrology_assets(scenario, mapping, FIXTURE)

    assert result.road_job_ids == ("R1",)
    assert result.watershed_ids == ("watershed-1",)
    assert len(result.assets) == 2
    assert result.to_dict()["asset_count"] == 2


def test_unknown_road_job_and_watershed_fail(tmp_path: Path) -> None:
    scenario, mapping = _mapping(tmp_path)
    payload = _payload()
    assets = payload["assets"]
    assert isinstance(assets, list)
    first = assets[0]
    assert isinstance(first, dict)
    first["road_job_id"] = "R99"
    with pytest.raises(FemicHydrologyAssetError, match="unknown road job"):
        map_hydrology_assets(
            scenario,
            mapping,
            _write(tmp_path / "bad-road.json", payload),
        )

    payload = _payload()
    assets = payload["assets"]
    assert isinstance(assets, list)
    second = assets[1]
    assert isinstance(second, dict)
    second["watershed_id"] = "watershed-99"
    with pytest.raises(FemicHydrologyAssetError, match="not in the hydrology mapping"):
        map_hydrology_assets(
            scenario,
            mapping,
            _write(tmp_path / "bad-watershed.json", payload),
        )


def test_validation_rejects_duplicates_and_bad_fields(tmp_path: Path) -> None:
    payload = _payload()
    assets = payload["assets"]
    assert isinstance(assets, list)
    payload["assets"] = [*assets, assets[0]]
    report = validate_hydrology_assets(_write(tmp_path / "duplicate.json", payload))
    assert report.is_valid is False
    assert any("Duplicate asset id" in error for error in report.errors)

    payload = _payload()
    payload["reviewer_id"] = None
    report = validate_hydrology_assets(_write(tmp_path / "reviewer.json", payload))
    assert any("reviewer_id" in error for error in report.errors)

    payload = _payload()
    assets = payload["assets"]
    assert isinstance(assets, list)
    first = assets[0]
    assert isinstance(first, dict)
    first["asset_type"] = "bridge"
    report = validate_hydrology_assets(_write(tmp_path / "type.json", payload))
    assert any("unsupported asset_type" in error for error in report.errors)

    payload = _payload()
    assets = payload["assets"]
    assert isinstance(assets, list)
    first = assets[0]
    assert isinstance(first, dict)
    first["road_job_id"] = None
    report = validate_hydrology_assets(_write(tmp_path / "road.json", payload))
    assert any("no road_job_id" in error for error in report.errors)


def test_cli_validate_and_map(tmp_path: Path) -> None:
    scenario, mapping = _mapping(tmp_path)
    validated = runner.invoke(
        app,
        ["scenario", "hydrology", "assets", "validate", str(FIXTURE)],
        prog_name="fhops",
    )
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output)["is_valid"] is True

    mapped = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "assets",
            "validate",
            str(FIXTURE),
            "--scenario",
            str(scenario),
            "--mapping",
            str(mapping),
        ],
        prog_name="fhops",
    )
    assert mapped.exit_code == 0, mapped.output
    assert json.loads(mapped.output)["asset_count"] == 2
