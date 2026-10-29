"""Terrain-aware routing tests for the ground-based system model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_ground_system import _system_scenario

from fhops.ground_system import GroundSystemError, simulate_ground_system


def _write_dem_and_road(tmp_path: Path) -> tuple[Path, Path]:
    rasterio = pytest.importorskip("rasterio")
    numpy = pytest.importorskip("numpy")
    x0, y0 = 881600.0, 627400.0
    width = height = 150
    pixel = 2.0
    transform = rasterio.transform.from_origin(x0, y0 + height * pixel, pixel, pixel)
    rows, cols = numpy.indices((height, width))
    y = y0 + height * pixel - (rows + 0.5) * pixel
    elevation = 412.0 + 0.15 * (y - y0)
    dem_path = tmp_path / "terrain.tif"
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:3005",
        transform=transform,
    ) as dataset:
        dataset.write(elevation.astype("float32"), 1)
    road = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[x0, 627550.0], [x0 + width * pixel, 627550.0]],
                },
            }
        ],
    }
    road_path = tmp_path / "road.geojson"
    road_path.write_text(json.dumps(road), encoding="utf-8")
    return dem_path, road_path


def test_ground_system_dem_and_road_routing(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    dem, road = _write_dem_and_road(tmp_path)
    result = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
        dem_path=dem,
        road_path=road,
        max_skidder_grade_percent=30.0,
    )
    terrain = result.rate_provenance["terrain"]
    assert isinstance(terrain, dict)
    assert terrain["dem_path"] == str(dem.resolve())
    assert terrain["road_path"] == str(road.resolve())
    travel = [event for event in result.events if event.type in {"travel_empty", "travel_loaded"}]
    assert travel
    assert all(event.distance_m > 0 for event in travel)
    assert any(event.max_grade_percent > 0 for event in travel)


def test_ground_system_refuses_steep_route(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    dem, road = _write_dem_and_road(tmp_path)
    with pytest.raises(GroundSystemError, match="maximum grade"):
        simulate_ground_system(
            scenario,
            block_id="B01",
            feller_machine_id="H1",
            skidder_machine_ids=("H2", "H3"),
            loader_machine_id="H4",
            bunch_volume_m3=1.0,
            dem_path=dem,
            road_path=road,
            max_skidder_grade_percent=5.0,
        )


def test_terrain_router_uses_connected_road_network(tmp_path: Path) -> None:
    pytest.importorskip("shapely")
    network = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 0]]},
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "LineString", "coordinates": [[10, 0], [20, 10]]},
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "LineString", "coordinates": [[10, 0], [20, -10]]},
            },
        ],
    }
    path = tmp_path / "network.geojson"
    path.write_text(json.dumps(network), encoding="utf-8")
    from fhops.terrain import TerrainRouter

    router = TerrainRouter(road_path=path)
    profile = router.route((0.0, 0.0), (20.0, 10.0))
    assert router.provenance()["road_model"] == "road network"
    assert profile.distance_m > 20.0
    router.close()
