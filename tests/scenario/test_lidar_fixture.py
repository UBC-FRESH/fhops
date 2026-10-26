"""Public TFL 6 LidarBC fixture tests (P14.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fhops.optimization.heuristics.sa import solve_sa
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.scenario.lidar_operability import assess_scenario_operability

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "examples/lidar_tfl6"

# WS4 P52 / FEMIC P79.9 shared-AOI parity rows; support values are rounded to six decimals.
EXPECTED = {
    "T6_23339490": (18.093685, 10.650112),
    "T6_23339461": (51.546347, 19.196865),
    "T6_23339462": (19.693197, 1.082238),
    "T6_23339458": (22.585566, 8.702228),
    "T6_16625195": (40.468577, 13.973793),
    "T6_16624698": (22.007911, 1.992587),
    "T6_19212607": (27.323784, 16.535896),
}


def test_fixture_loads_and_has_expected_shape() -> None:
    scenario = load_scenario(FIXTURE / "scenario.yaml")
    assert scenario.name == "TFL 6 LidarBC Public Fixture"
    assert len(scenario.blocks) == 7
    assert len(scenario.landings) == 1
    assert scenario.lidar_products is not None
    assert scenario.lidar_products[0].bundle_id == "lidarbc-995fb1f771f4d7fe"
    assert scenario.lidar_products[0].licence_id == "OGL-BC"
    assert scenario.lidar_support is not None
    assert len(scenario.lidar_support) == 18


def test_fixture_values_match_ws4_parity() -> None:
    scenario = load_scenario(FIXTURE / "scenario.yaml")
    slope = {
        row.support_id: row.slope_percent
        for row in scenario.lidar_support or []
        if row.support_unit == "block" and row.product == "slope"
    }
    canopy = {
        row.support_id: row.canopy_height_m
        for row in scenario.lidar_support or []
        if row.support_unit == "block" and row.product == "chm"
    }
    for block_id, (expected_slope, expected_canopy) in EXPECTED.items():
        assert slope[block_id] == pytest.approx(expected_slope, abs=1e-6)
        assert canopy[block_id] == pytest.approx(expected_canopy, abs=1e-6)
    assert all(
        block.ground_slope_percent == pytest.approx(EXPECTED[block.id][0], abs=1e-3)
        for block in scenario.blocks
    )


def test_provenance_records_bundle_and_licence() -> None:
    payload = json.loads((FIXTURE / "provenance.json").read_text(encoding="utf-8"))
    assert payload["bundle_id"] == "lidarbc-995fb1f771f4d7fe"
    assert payload["bundle_version"] == "2026.10.0-tfl6-pilot"
    assert payload["licence_id"] == "OGL-BC"
    assert payload["manifest_sha256"]
    assert payload["products"]["slope"]["crs"] == "EPSG:3005"
    assert payload["synthetic_tables"]["productivity_rate_m3_per_day"] == 500.0


def test_operability_exposes_cable_mismatch_and_fallbacks() -> None:
    scenario = load_scenario(FIXTURE / "scenario.yaml")
    rows = {row.block_id: row for row in assess_scenario_operability(scenario)}
    cable = rows["T6_23339461"]
    assert cable.terrain_class == "cable"
    assert cable.current_system_id == "ground_fb_skid"
    assert cable.current_system_compatible is False
    assert cable.recommended_system_id.startswith("cable_")
    assert "class_average_roughness" in cable.fallbacks
    ground = rows["T6_23339490"]
    assert ground.terrain_class == "ground"
    assert ground.current_system_compatible is True


def test_fixture_smoke_solve() -> None:
    scenario = load_scenario(FIXTURE / "scenario.yaml")
    result = solve_sa(Problem.from_scenario(scenario), iters=20, seed=7)
    assert isinstance(result["objective"], float)
    assert not result["assignments"].empty
    assert set(result["assignments"]["block_id"]).issubset({block.id for block in scenario.blocks})
