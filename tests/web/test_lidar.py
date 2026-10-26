"""LiDAR evidence API and map-layer tests for the web UI."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from fhops.web.app import ServiceConfig, create_app

REPO = Path(__file__).resolve().parents[2]
LIDAR_SCENARIO = REPO / "examples/lidar_tfl6/scenario.yaml"


def _client(tmp_path: Path, *, scenario: Path = LIDAR_SCENARIO) -> TestClient:
    run_dir = tmp_path / "runs" / "lidar-run"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "run_id": "lidar-run",
                "domain": "operational",
                "run_type": "solve_heur",
                "status": "ok",
                "scenario": str(scenario),
            }
        ),
        encoding="utf-8",
    )
    app = create_app(
        ServiceConfig(
            roots=[tmp_path / "runs"],
            workspace=tmp_path,
            geometry=None,
        )
    )
    return TestClient(app)


def test_lidar_payload_for_public_fixture(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/runs/lidar-run/lidar")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is True
    assert payload["support_available"] is True
    assert payload["bundle"]["bundle_id"] == "lidarbc-995fb1f771f4d7fe"
    assert payload["bundle"]["licence_id"] == "OGL-BC"
    assert payload["coverage"]["blocks"] == 7
    assert payload["coverage"]["support_rows"] == 18
    assert payload["coverage"]["terrain_classes"]["cable"] == 2
    assert payload["coverage"]["terrain_classes"]["ground"] == 5
    cable = next(block for block in payload["blocks"] if block["block_id"] == "T6_23339461")
    assert cable["terrain_class"] == "cable"
    assert cable["operability"]["current_system_compatible"] is False
    assert "class_average_roughness" in cable["operability"]["fallbacks"]


def test_lidar_unavailable_for_plain_scenario(tmp_path: Path) -> None:
    client = _client(tmp_path, scenario=REPO / "examples/tiny7/scenario.yaml")
    payload = client.get("/api/runs/lidar-run/lidar").json()
    assert payload["available"] is False
    assert payload["blocks"] == []
    assert any("no lidar" in warning.lower() for warning in payload["warnings"])


def test_lidar_layers_and_map(tmp_path: Path) -> None:
    client = _client(tmp_path)
    layers = client.get("/api/runs/lidar-run/layers").json()["layers"]
    by_name = {layer["name"]: layer for layer in layers}
    assert by_name["lidar_operability"]["available"] is True
    assert by_name["lidar_slope"]["available"] is True
    assert by_name["lidar_canopy"]["available"] is True

    payload = client.get("/api/runs/lidar-run/map?layers=lidar_operability").json()
    assert len(payload["features"]) == 7
    cable = next(
        feature
        for feature in payload["features"]
        if feature["properties"]["block_id"] == "T6_23339461"
    )
    assert cable["properties"]["terrain_class"] == "cable"
    assert cable["properties"]["current_system_compatible"] is False


def test_lidar_panel_in_skins_and_reviewer_read_only(tmp_path: Path) -> None:
    client = _client(tmp_path)
    planner = client.get("/api/skins/operational-planner").json()
    reviewer = client.get("/api/skins/reviewer").json()
    assert "lidar" in planner["panels"]
    assert "lidar" in reviewer["panels"]
    assert "lidar_operability" in reviewer["layers"]
    assert reviewer["read_only"] is True
    assert "edit_objective" not in reviewer["actions"]
