"""FEMIC LidarBC product-to-scenario mapping tests (P14.3)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("geopandas")
pytest.importorskip("rasterio")

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import box  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from fhops.cli.main import app  # noqa: E402
from fhops.scenario.io import load_scenario  # noqa: E402
from fhops.scenario.lidar_mapping import (  # noqa: E402
    FemicLidarMappingError,
    map_femic_lidar_to_scenario,
)
from fhops.scenario.lidar_registration import register_femic_lidar_bundle  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scenario(tmp_path: Path) -> Path:
    target = tmp_path / "tiny7"
    shutil.copytree(REPO / "examples/tiny7", target)
    scenario = target / "scenario.yaml"
    blocks = gpd.GeoDataFrame(
        {"block_id": ["B01", "B02"]},
        geometry=[box(0, 0, 3, 3), box(0, 0, 1, 1)],
        crs="EPSG:3005",
    )
    landings = gpd.GeoDataFrame(
        {"landing_id": ["L1", "L2"]},
        geometry=[box(0, 0, 1, 1), box(2, 2, 3, 3)],
        crs="EPSG:3005",
    )
    blocks.to_file(target / "blocks.geojson", driver="GeoJSON")
    landings.to_file(target / "landings.geojson", driver="GeoJSON")
    scenario.write_text(
        scenario.read_text(encoding="utf-8")
        + "\ngeo_block_path: blocks.geojson\n"
        + "geo_landing_path: landings.geojson\n"
        + "geo_crs: EPSG:3005\n",
        encoding="utf-8",
    )
    return scenario


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    products = root / "products"
    products.mkdir(parents=True)
    values = np.array([[10.0, 20.0, 30.0], [40.0, 50.0, 60.0], [70.0, 80.0, 90.0]])
    records = []
    for name in ("slope", "chm"):
        path = products / f"{name}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=3,
            height=3,
            count=1,
            dtype="float32",
            crs="EPSG:3005",
            transform=from_origin(0, 3, 1, 1),
            nodata=-9999.0,
        ) as dataset:
            dataset.write(values, 1)
        records.append(
            {
                "product": name,
                "relative_path": f"products/{name}.tif",
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "crs": "EPSG:3005",
                "resolution_m": 1.0,
                "vertical_datum": "CGVD2013",
                "licence_id": "OGL-BC",
                "source_tile_ids": ["lidarbc:5:1"],
                "derived": True,
                "lineage": ["test"],
            }
        )
    manifest = {
        "schema_version": "femic.lidar.product.v1",
        "layout_version": "femic.lidar.bundle.v1",
        "bundle_id": "lidarbc-map-test",
        "bundle_version": "test-1",
        "source": {
            "source_id": "lidarbc",
            "licence_id": "OGL-BC",
            "native_crs": "EPSG:3005",
        },
        "selection": {
            "sha256": "a" * 64,
            "tile_ids": ["lidarbc:5:1"],
            "products": ["slope", "chm"],
        },
        "processing": {"version": "test"},
        "summary": {
            "product_count": len(records),
            "total_bytes": sum(record["size_bytes"] for record in records),
        },
        "products": records,
        "consumer_contract": {"manifest_path": "manifest.json"},
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_map_products_to_block_and_landing_support(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    register_femic_lidar_bundle(scenario_path, bundle)

    result = map_femic_lidar_to_scenario(scenario_path, bundle)
    assert result.written is True
    assert len(result.rows) == 8
    assert {row.support_unit for row in result.rows} == {"block", "landing"}
    assert {row.product for row in result.rows} == {"slope", "chm"}
    block_slope = next(
        row
        for row in result.rows
        if row.support_unit == "block" and row.support_id == "B01" and row.product == "slope"
    )
    assert block_slope.slope_percent == pytest.approx(50.0)
    assert block_slope.native_resolution_m == 1.0
    assert block_slope.aggregation == "mean"
    assert block_slope.valid_pixels == 9
    assert block_slope.support_area_m2 == pytest.approx(9.0)

    loaded = load_scenario(scenario_path)
    assert loaded.lidar_support is not None
    assert len(loaded.lidar_support) == 8


def test_map_twice_replaces_rows_without_duplicates(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    register_femic_lidar_bundle(scenario_path, bundle)
    first = map_femic_lidar_to_scenario(scenario_path, bundle)
    second = map_femic_lidar_to_scenario(scenario_path, bundle)
    assert len(first.rows) == len(second.rows) == 8
    assert len(load_scenario(scenario_path).lidar_support or []) == 8


def test_map_dry_run_preserves_scenario(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    register_femic_lidar_bundle(scenario_path, bundle)
    before = scenario_path.read_text(encoding="utf-8")
    result = map_femic_lidar_to_scenario(scenario_path, bundle, dry_run=True)
    assert result.written is False
    assert scenario_path.read_text(encoding="utf-8") == before


def test_map_requires_registered_pin(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    with pytest.raises(FemicLidarMappingError, match="not pinned"):
        map_femic_lidar_to_scenario(scenario_path, bundle)


def test_map_missing_product_is_explicit(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    register_femic_lidar_bundle(scenario_path, bundle)
    with pytest.raises(FemicLidarMappingError, match="no product"):
        map_femic_lidar_to_scenario(scenario_path, bundle, products={"aspect": "aspect_degrees"})


def test_cli_map(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    register_femic_lidar_bundle(scenario_path, bundle)
    result = CliRunner().invoke(
        app,
        [
            "scenario",
            "lidar",
            "map",
            str(scenario_path),
            str(bundle),
            "--statistic",
            "p95",
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    assert '"written": true' in result.output
    loaded = load_scenario(scenario_path)
    assert loaded.lidar_support is not None
    assert all(row.aggregation == "p95" for row in loaded.lidar_support)
