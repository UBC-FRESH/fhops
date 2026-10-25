"""Scenario-level FEMIC LidarBC pin/support contract tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from fhops.scenario.contract import LidarSupport
from fhops.scenario.io import load_scenario

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests/fixtures/lidar"


def _scenario_with_fragment(tmp_path: Path, suffix: str = "") -> Path:
    target = tmp_path / "tiny7"
    shutil.copytree(REPO / "examples/tiny7", target)
    scenario = target / "scenario.yaml"
    fragment = (FIXTURE / "scenario_fragment.yaml").read_text(encoding="utf-8")
    scenario.write_text(
        scenario.read_text(encoding="utf-8") + "\n" + fragment + suffix, encoding="utf-8"
    )
    return scenario


def test_scenario_pin_and_support_round_trip(tmp_path: Path) -> None:
    scenario = load_scenario(_scenario_with_fragment(tmp_path))
    assert scenario.lidar_products is not None
    pin = scenario.lidar_products[0]
    assert pin.bundle_id == "lidarbc-tfl6-2026.10"
    assert pin.bundle_version == "2026.10.0-tfl6"
    assert pin.manifest_sha256 == "b" * 64
    assert pin.licence_id == "OGL-BC"
    assert scenario.lidar_support is not None
    block = next(row for row in scenario.lidar_support if row.support_unit == "block")
    assert block.support_id == "B01"
    assert block.product == "slope"
    assert block.native_resolution_m == 1.0
    assert block.valid_pixels == 12000
    assert block.canopy_cover_percent == 62.0
    assert block.vertical_structure_class == "multi_layer"
    assert {row.support_unit for row in scenario.lidar_support} == {"block", "landing", "road"}


def test_existing_scenario_without_lidar_is_unchanged() -> None:
    scenario = load_scenario(REPO / "examples/tiny7/scenario.yaml")
    assert scenario.lidar_products is None
    assert scenario.lidar_support is None


def test_support_rejects_out_of_range_aspect() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 360"):
        LidarSupport(
            support_unit="block",
            support_id="B01",
            bundle_id="b",
            bundle_version="1",
            product="slope",
            native_resolution_m=1.0,
            aspect_degrees=400.0,
        )


def test_unpinned_bundle_is_rejected(tmp_path: Path) -> None:
    suffix = """  - support_unit: block
    support_id: B02
    bundle_id: lidarbc-other
    bundle_version: 2026.11.0
    product: slope
    native_resolution_m: 1.0
"""
    with pytest.raises(ValueError, match="unpinned FEMIC bundle"):
        load_scenario(_scenario_with_fragment(tmp_path, suffix))


def test_unknown_block_support_is_rejected(tmp_path: Path) -> None:
    suffix = """  - support_unit: block
    support_id: B99
    bundle_id: lidarbc-tfl6-2026.10
    bundle_version: 2026.10.0-tfl6
    product: slope
    native_resolution_m: 1.0
"""
    with pytest.raises(ValueError, match="unknown block_id=B99"):
        load_scenario(_scenario_with_fragment(tmp_path, suffix))


def test_duplicate_pin_is_rejected(tmp_path: Path) -> None:
    scenario = _scenario_with_fragment(tmp_path)
    duplicate = (
        "lidar_products:\n  - bundle_id: lidarbc-tfl6-2026.10\n    bundle_version: 2026.10.0-tfl6\n"
    )
    scenario.write_text(
        scenario.read_text(encoding="utf-8").replace("lidar_products:\n", duplicate, 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate LidarProductRef"):
        load_scenario(scenario)
