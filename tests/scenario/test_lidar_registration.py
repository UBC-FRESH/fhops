"""FEMIC bundle registration and CLI tests (P14.2)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.io import load_scenario
from fhops.scenario.lidar_registration import (
    FemicLidarRegistrationError,
    register_femic_lidar_bundle,
)

REPO = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path, *, crs: str = "EPSG:3005") -> Path:
    root = tmp_path / "bundle"
    products = root / "products"
    products.mkdir(parents=True)
    product = products / "slope.tif"
    product.write_bytes(b"synthetic slope raster")
    manifest = {
        "schema_version": "femic.lidar.product.v1",
        "layout_version": "femic.lidar.bundle.v1",
        "bundle_id": "lidarbc-test",
        "bundle_version": "test-1",
        "source": {
            "source_id": "lidarbc",
            "licence_id": "OGL-BC",
            "native_crs": crs,
        },
        "selection": {
            "sha256": "a" * 64,
            "tile_ids": ["lidarbc:5:1"],
            "products": ["slope"],
        },
        "processing": {"version": "test"},
        "summary": {"product_count": 1, "total_bytes": product.stat().st_size},
        "products": [
            {
                "product": "slope",
                "relative_path": "products/slope.tif",
                "sha256": _sha256(product),
                "size_bytes": product.stat().st_size,
                "crs": crs,
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
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _scenario(tmp_path: Path) -> Path:
    target = tmp_path / "hauling"
    shutil.copytree(REPO / "examples/hauling", target)
    return target / "scenario.yaml"


def test_register_pins_bundle_and_aoi(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    result = register_femic_lidar_bundle(scenario_path, bundle)
    assert result.written is True
    assert result.pin.bundle_id == "lidarbc-test"
    assert result.pin.manifest_sha256 is not None
    assert result.pin.aoi_bbox is not None
    assert result.pin.products is not None
    assert result.pin.products[0].sha256 == result.pin.products[0].sha256.lower()

    loaded = load_scenario(scenario_path)
    assert loaded.lidar_products is not None
    pin = loaded.lidar_products[0]
    assert pin.bundle_version == "test-1"
    assert pin.crs == "EPSG:3005"
    assert pin.aoi_bbox is not None
    assert pin.products is not None
    assert pin.products[0].relative_path == "products/slope.tif"


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    before = scenario_path.read_text(encoding="utf-8")
    result = register_femic_lidar_bundle(scenario_path, _bundle(tmp_path), dry_run=True)
    assert result.written is False
    assert scenario_path.read_text(encoding="utf-8") == before


def test_crs_mismatch_is_rejected(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    with pytest.raises(FemicLidarRegistrationError, match="CRS"):
        register_femic_lidar_bundle(scenario_path, _bundle(tmp_path, crs="EPSG:4326"))


def test_corrupt_bundle_is_rejected(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    (bundle / "products/slope.tif").write_bytes(b"tampered")
    with pytest.raises(FemicLidarRegistrationError, match="checksum"):
        register_femic_lidar_bundle(scenario_path, bundle)


def test_cli_validate_and_register(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = _bundle(tmp_path)
    runner = CliRunner()
    validate = runner.invoke(app, ["scenario", "lidar", "validate", str(bundle)], prog_name="fhops")
    assert validate.exit_code == 0, validate.output
    assert '"is_valid": true' in validate.output

    register = runner.invoke(
        app,
        ["scenario", "lidar", "register", str(scenario_path), str(bundle)],
        prog_name="fhops",
    )
    assert register.exit_code == 0, register.output
    assert '"written": true' in register.output
    assert load_scenario(scenario_path).lidar_products is not None
