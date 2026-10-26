"""Advisory terrain/canopy operability tests (P14.4)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.contract import LidarSupport
from fhops.scenario.io import load_scenario
from fhops.scenario.lidar_operability import (
    OperabilityRules,
    assess_block_operability,
    assess_scenario_operability,
)

REPO = Path(__file__).resolve().parents[2]


def _scenario(tmp_path: Path, rows: list[LidarSupport] | None = None):
    target = tmp_path / "tiny7"
    shutil.copytree(REPO / "examples/tiny7", target)
    scenario_path = target / "scenario.yaml"
    if rows:
        payload = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
        payload["lidar_support"] = [row.model_dump(mode="json", exclude_none=True) for row in rows]
        scenario_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return scenario_path, load_scenario(scenario_path)


def _row(block_id: str, **kwargs) -> LidarSupport:
    payload = {
        "support_unit": "block",
        "support_id": block_id,
        "bundle_id": "lidarbc-test",
        "bundle_version": "test-1",
        "product": "slope",
        "native_resolution_m": 1.0,
    }
    payload.update(kwargs)
    return LidarSupport.model_validate(payload)


def test_cable_block_is_explicit_and_current_system_incompatible(tmp_path: Path) -> None:
    _, scenario = _scenario(
        tmp_path,
        [
            _row("B01", slope_percent=45.0, roughness_m=0.2, canopy_cover_percent=60.0),
            _row("B02", product="slope", slope_percent=10.0, roughness_m=0.1),
        ],
    )
    blocks = [
        block.model_copy(update={"harvest_system_id": "ground_fb_skid"})
        for block in scenario.blocks
    ]
    scenario = scenario.model_copy(update={"blocks": blocks})
    rows = {row.block_id: row for row in assess_scenario_operability(scenario)}
    assert rows["B01"].terrain_class == "cable"
    assert rows["B01"].current_system_compatible is False
    assert rows["B01"].recommended_system_id == "cable_running_tr122_clearcut"
    assert rows["B01"].move_in_multiplier > 1.0
    assert rows["B02"].terrain_class == "ground"
    assert rows["B02"].current_system_compatible is True
    assert rows["B02"].recommended_system_id == "ground_fb_skid"


def test_helicopter_class_is_explicit(tmp_path: Path) -> None:
    _, scenario = _scenario(tmp_path, [_row("B01", slope_percent=72.0)])
    result = assess_block_operability(scenario, "B01")
    assert result.terrain_class == "helicopter"
    assert result.recommended_system_id == "helicopter"
    assert "helicopter class is explicit" in " ".join(result.reasons)


def test_fallbacks_are_labelled(tmp_path: Path) -> None:
    _, scenario = _scenario(tmp_path)
    result = assess_block_operability(scenario, "B01")
    assert result.terrain_class == "ground"
    assert result.current_system_compatible is True
    assert result.evidence_source == "block.ground_slope_percent"
    assert "class_average_roughness" in result.fallbacks
    assert result.slope_percent == pytest.approx(6.48)


def test_landing_slope_can_drive_classification(tmp_path: Path) -> None:
    _, scenario = _scenario(
        tmp_path,
        [
            _row("B01", slope_percent=None),
            _row("L1", support_unit="landing", product="slope", slope_percent=40.0),
        ],
    )
    result = assess_block_operability(scenario, "B01")
    assert result.landing_slope_percent == pytest.approx(40.0)
    assert result.terrain_class == "cable"
    assert result.landing_multiplier > 1.0


def test_cli_json_report(tmp_path: Path) -> None:
    scenario_path, _ = _scenario(
        tmp_path,
        [
            _row("B01", slope_percent=45.0),
            _row("B02", slope_percent=8.0),
        ],
    )
    result = CliRunner().invoke(
        app,
        ["scenario", "lidar", "operability", str(scenario_path), "--json"],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert {row["block_id"]: row["terrain_class"] for row in rows} == {
        "B01": "cable",
        "B02": "ground",
    }
    assert rows[0]["cost_context"]["basis"].startswith("advisory")


def test_custom_thresholds_are_visible(tmp_path: Path) -> None:
    _, scenario = _scenario(tmp_path, [_row("B01", slope_percent=30.0)])
    result = assess_block_operability(
        scenario, "B01", rules=OperabilityRules(ground_max_slope_percent=25.0)
    )
    assert result.terrain_class == "cable"
