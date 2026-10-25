from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from fhops.scenario.lidar import (
    FemicLidarError,
    bundle_pin,
    load_femic_lidar_bundle,
    summarize_femic_lidar_for_polygons,
    validate_femic_lidar_bundle,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    products = root / "products"
    products.mkdir(parents=True)
    raster_path = products / "slope__01__slope.tif"
    values = np.array([[10.0, 20.0, 30.0], [40.0, 50.0, 60.0], [70.0, 80.0, 90.0]])
    with rasterio.open(
        raster_path,
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
    manifest = {
        "schema_version": "femic.lidar.product.v1",
        "layout_version": "femic.lidar.bundle.v1",
        "bundle_id": "lidarbc-test",
        "bundle_version": "test-1",
        "source": {
            "source_id": "lidarbc",
            "licence_id": "OGL-BC",
            "native_crs": "EPSG:3005",
        },
        "selection": {
            "sha256": "a" * 64,
            "tile_ids": ["lidarbc:5:1"],
            "products": ["slope"],
        },
        "processing": {"version": "test"},
        "summary": {"product_count": 1, "total_bytes": raster_path.stat().st_size},
        "products": [
            {
                "product": "slope",
                "relative_path": "products/slope__01__slope.tif",
                "sha256": _sha256(raster_path),
                "size_bytes": raster_path.stat().st_size,
                "crs": "EPSG:3005",
                "resolution_m": 1.0,
                "vertical_datum": "CGVD2013",
                "licence_id": "OGL-BC",
                "source_tile_ids": ["lidarbc:5:1"],
                "derived": True,
                "lineage": ["test"],
            }
        ],
        "consumer_contract": {"manifest_path": "manifest.json"},
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def test_load_and_pin_bundle(tmp_path: Path) -> None:
    root = _bundle(tmp_path)

    bundle = load_femic_lidar_bundle(
        root,
        expected_bundle_id="lidarbc-test",
        expected_bundle_version="test-1",
    )

    assert bundle.bundle_id == "lidarbc-test"
    assert bundle.products["slope"].crs == "EPSG:3005"
    assert bundle.products["slope"].resolution_m == 1.0
    pin = bundle_pin(bundle)
    assert pin["bundle_id"] == "lidarbc-test"
    assert pin["products"]["slope"]["sha256"]
    assert validate_femic_lidar_bundle(root).is_valid


def test_tampered_bundle_is_rejected(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    (root / "products/slope__01__slope.tif").write_bytes(b"tampered")

    report = validate_femic_lidar_bundle(root)
    assert not report.is_valid
    assert any("checksum" in error for error in report.errors)
    with pytest.raises(FemicLidarError, match="Invalid FEMIC"):
        load_femic_lidar_bundle(root)


def test_expected_pin_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _bundle(tmp_path)

    with pytest.raises(FemicLidarError, match="Bundle id"):
        load_femic_lidar_bundle(root, expected_bundle_id="other")


def test_polygon_summary(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    bundle = load_femic_lidar_bundle(root)
    polygons = gpd.GeoDataFrame(
        {"feature_id": ["p1"]},
        geometry=[box(0, 0, 3, 3)],
        crs="EPSG:3005",
    )
    polygon_path = tmp_path / "polygons.geojson"
    polygons.to_file(polygon_path, driver="GeoJSON")

    summaries = summarize_femic_lidar_for_polygons(
        bundle,
        polygon_path,
        id_field="feature_id",
    )

    assert len(summaries) == 1
    assert summaries[0].polygon_id == "p1"
    assert summaries[0].valid_pixels == 9
    assert summaries[0].statistics["mean"] == pytest.approx(50.0)
    assert summaries[0].statistics["p95"] == pytest.approx(86.0)


def test_polygon_summary_rejects_crs_mismatch(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    bundle = load_femic_lidar_bundle(root)
    polygons = gpd.GeoDataFrame(
        {"feature_id": ["p1"]},
        geometry=[box(0, 0, 3, 3)],
        crs="EPSG:4326",
    )
    polygon_path = tmp_path / "polygons.geojson"
    polygons.to_file(polygon_path, driver="GeoJSON")

    with pytest.raises(FemicLidarError, match="CRS"):
        summarize_femic_lidar_for_polygons(bundle, polygon_path)
