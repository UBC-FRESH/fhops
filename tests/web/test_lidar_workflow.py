"""LiDAR bundle workflow endpoint tests."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from fhops.scenario.io import load_scenario
from fhops.web.app import ServiceConfig, create_app

REPO = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(root: Path) -> Path:
    bundle = root / "bundle"
    products = bundle / "products"
    products.mkdir(parents=True)
    product = products / "slope.tif"
    product.write_bytes(b"synthetic slope grid")
    manifest = {
        "schema_version": "femic.lidar.product.v1",
        "layout_version": "femic.lidar.bundle.v1",
        "bundle_id": "lidarbc-web-test",
        "bundle_version": "test-1",
        "source": {"source_id": "lidarbc", "licence_id": "OGL-BC", "native_crs": "EPSG:3005"},
        "selection": {"sha256": "a" * 64, "tile_ids": ["lidarbc:1:1"], "products": ["slope"]},
        "processing": {"version": "test"},
        "summary": {"product_count": 1, "total_bytes": product.stat().st_size},
        "products": [
            {
                "product": "slope",
                "relative_path": "products/slope.tif",
                "sha256": _sha256(product),
                "size_bytes": product.stat().st_size,
                "crs": "EPSG:3005",
                "resolution_m": 1.0,
                "vertical_datum": "CGVD2013",
                "licence_id": "OGL-BC",
                "source_tile_ids": ["lidarbc:1:1"],
                "derived": True,
                "lineage": ["test"],
            }
        ],
        "consumer_contract": {"manifest_path": "manifest.json"},
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def _client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    bundle = _bundle(bundles)
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text((REPO / "examples/tiny7/scenario.yaml").read_text(encoding="utf-8"))
    # The scenario data paths must remain valid after copying.
    data = tmp_path / "data"
    import shutil

    shutil.copytree(REPO / "examples/tiny7/data", data)
    (tmp_path / "tiny7_block_distances.csv").write_text(
        (REPO / "examples/tiny7/tiny7_block_distances.csv").read_text(encoding="utf-8")
    )
    run_dir = tmp_path / "runs" / "run-a"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "run_id": "run-a",
                "domain": "operational",
                "run_type": "solve_heur",
                "status": "ok",
                "scenario": str(scenario),
            }
        ),
        encoding="utf-8",
    )
    fake = tmp_path / "fake_cli.py"
    args_file = tmp_path / "args.json"
    fake.write_text(
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(args_file)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        "print(json.dumps({'written': True, 'rows': [], 'warnings': []}))\n",
        encoding="utf-8",
    )
    app = create_app(
        ServiceConfig(
            roots=[tmp_path / "runs"],
            workspace=tmp_path,
            lidar_bundles=[bundles],
            cli_command=(sys.executable, str(fake)),
        )
    )
    return TestClient(app), bundle, args_file


def test_bundle_listing_validate_and_register(tmp_path: Path) -> None:
    client, bundle, _ = _client(tmp_path)
    listing = client.get("/api/lidar/bundles")
    assert listing.status_code == 200
    assert listing.json()["bundles"][0]["name"] == "bundle"

    validate = client.post(
        "/api/runs/run-a/lidar/validate",
        json={"bundle": "bundle", "expected_bundle_id": "lidarbc-web-test"},
    )
    assert validate.status_code == 200, validate.text
    assert validate.json()["is_valid"] is True

    register = client.post(
        "/api/runs/run-a/lidar/register",
        json={"bundle": "bundle"},
    )
    assert register.status_code == 200, register.text
    assert register.json()["written"] is True
    loaded = load_scenario(tmp_path / "scenario.yaml")
    assert loaded.lidar_products is not None
    assert loaded.lidar_products[0].bundle_id == "lidarbc-web-test"
    assert bundle.is_dir()


def test_map_runs_cli_subprocess(tmp_path: Path) -> None:
    client, _, args_file = _client(tmp_path)
    response = client.post(
        "/api/runs/run-a/lidar/map",
        json={"bundle": "bundle", "statistic": "mean"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["written"] is True
    args = json.loads(args_file.read_text())
    assert args[:3] == ["scenario", "lidar", "map"]
    assert str(tmp_path / "scenario.yaml") in args
    assert "--statistic" in args


def test_bundle_and_roads_escape_are_rejected(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    bad_bundle = client.post(
        "/api/runs/run-a/lidar/validate",
        json={"bundle": "../outside"},
    )
    assert bad_bundle.status_code == 400
    bad_roads = client.post(
        "/api/runs/run-a/lidar/map",
        json={"bundle": "bundle", "roads_geojson": "../../outside.geojson"},
    )
    assert bad_roads.status_code == 400
