"""Tests for the optional FastAPI service."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fhops.web.app import ServiceConfig, create_app, is_loopback, validate_bind


def _write(run_dir: Path, name: str, text: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / name).write_text(text, encoding="utf-8")


def _geometry(root: Path) -> Path:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"block_id": "b1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"block_id": "b2"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]],
                },
            },
        ],
    }
    path = root / "blocks.geojson"
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")
    return path


def _operational_run(root: Path) -> Path:
    run_dir = root / "op"
    _write(
        run_dir,
        "assignments.csv",
        "machine_id,block_id,day,shift_id,assigned,production\n"
        "m1,b1,1,DAY,1,100\nm2,b2,1,NIGHT,1,200\n",
    )
    _write(run_dir, "day_summary.csv", "day,production\n1,300\n")
    _write(run_dir, "kpis.json", '{"total_production": 300, "cost": 12.5}\n')
    _write(run_dir, "summary.json", '{"status": "optimal", "objective": 12.5}\n')
    return run_dir


def _hauling_run(root: Path) -> Path:
    run_dir = root / "haul"
    _write(run_dir, "haul_flows.csv", "day,block_id,yard_id,sorted_m3\n1,b1,y1,45\n2,b2,y1,60\n")
    _write(run_dir, "haul_truckloads.csv", "day,block_id,total_truckloads\n1,b1,1\n")
    _write(run_dir, "haul_schedule.csv", "load_id,truck_id,delivery_finish\nL1,t1,200\n")
    _write(run_dir, "haul_yard_inventory.csv", "day,yard_id,water_inventory_m3\n1,y1,0\n")
    _write(run_dir, "haul_contractor_workload.csv", "day,contractor_id,truckloads\n1,c1,2\n")
    _write(run_dir, "haul_truck_summary.csv", "truck_id,used,loads\nt1,true,2\n")
    _write(run_dir, "haul_loader_summary.csv", "loader_id,loads\nldr1,2\n")
    _write(run_dir, "haul_kpis.json", '{"objective": 1000, "loads": 2}\n')
    _write(run_dir, "haul_summary.json", '{"status": "optimal", "objective": 1000}\n')
    return run_dir


def _tactical_run(root: Path) -> Path:
    run_dir = root / "tac"
    _write(run_dir, "harvest_decisions.csv", "period_id,block_id,area_ha\np1,b1,10\n")
    _write(run_dir, "production.csv", "period_id,block_id,product_id,volume_m3\np1,b1,fir,100\n")
    _write(
        run_dir,
        "flows.csv",
        "period_id,origin_id,destination_id,product_id,volume_m3\np1,b1,f1,fir,100\n",
    )
    _write(run_dir, "inventory.csv", "period_id,facility_id,product_id,closing_m3\np1,f1,fir,10\n")
    _write(run_dir, "purchases.csv", "period_id,destination_id,product_id,volume_m3\n")
    _write(run_dir, "roads.csv", "period_id,road_id,built\np1,r1,1\n")
    _write(run_dir, "silviculture.csv", "period_id,block_id,treatment\np1,b1,plant\n")
    _write(run_dir, "fleet.csv", "period_id,system_id,units\np1,ground,2\n")
    _write(run_dir, "summary.json", '{"status": "optimal", "objective": 5000}\n')
    return run_dir


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    _operational_run(tmp_path)
    _hauling_run(tmp_path)
    _tactical_run(tmp_path)
    geometry = _geometry(tmp_path)
    app = create_app(ServiceConfig(roots=[tmp_path], host="127.0.0.1", geometry=geometry))
    return TestClient(app)


def test_health_and_run_discovery(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert "operational-planner" in health.json()["skins"]

    runs = client.get("/api/runs").json()
    assert {row["run_id"] for row in runs} == {"op", "haul", "tac"}
    assert {row["domain"] for row in runs} == {
        "operational",
        "hauling",
        "tactical_operational",
    }

    detail = client.get("/api/runs/haul")
    assert detail.status_code == 200
    assert detail.json()["domain"] == "hauling"
    assert client.get("/api/runs/nope").status_code == 404


def test_operational_endpoints(client: TestClient) -> None:
    summary = client.get("/api/runs/op/summary")
    assert summary.status_code == 200
    assert summary.json()["status"] == "optimal"

    assignments = client.get("/api/runs/op/assignments?day=1&shift=DAY").json()
    assert assignments["total"] == 1
    assert assignments["rows"][0]["machine_id"] == "m1"

    playback = client.get("/api/runs/op/playback?scope=day").json()
    assert playback["total"] == 1

    kpis = client.get("/api/runs/op/kpis").json()
    assert kpis["total_production"] == 300

    bad_filter = client.get("/api/runs/op/assignments?machine=m1&day=1")
    assert bad_filter.status_code == 200


def test_hauling_endpoints(client: TestClient) -> None:
    flows = client.get("/api/runs/haul/hauling/flows?day=1").json()
    assert flows["total"] == 1
    assert flows["rows"][0]["block_id"] == "b1"

    schedule = client.get("/api/runs/haul/hauling/schedule").json()
    assert schedule["rows"][0]["load_id"] == "L1"

    yard = client.get("/api/runs/haul/hauling/yard-inventory").json()
    assert yard["total"] == 1

    workload = client.get("/api/runs/haul/hauling/contractor-workload").json()
    assert workload["rows"][0]["contractor_id"] == "c1"

    trucks = client.get("/api/runs/haul/hauling/trucks").json()
    assert trucks["rows"][0]["truck_id"] == "t1"

    kpis = client.get("/api/runs/haul/kpis").json()
    assert kpis["loads"] == 2


def test_tactical_endpoints(client: TestClient) -> None:
    harvest = client.get("/api/runs/tac/tactical/harvest?period=p1").json()
    assert harvest["rows"][0]["block_id"] == "b1"

    production = client.get("/api/runs/tac/tactical/production?product=fir").json()
    assert production["total"] == 1

    flows = client.get("/api/runs/tac/tactical/flows?facility=f1").json()
    assert flows["total"] == 1

    for endpoint in (
        "inventory",
        "purchases",
        "roads",
        "silviculture",
        "fleet",
    ):
        response = client.get(f"/api/runs/tac/tactical/{endpoint}")
        assert response.status_code == 200, endpoint


def test_missing_artefact_is_named(client: TestClient) -> None:
    response = client.get("/api/runs/op/hauling/flows")
    assert response.status_code == 404
    assert "haul_flows" in response.json()["detail"]


def test_reports_listing_and_download(client: TestClient) -> None:
    reports = client.get("/api/runs/op/reports").json()
    assert any(report["path"] == "assignments.csv" for report in reports["reports"])

    download = client.get("/api/runs/op/reports/assignments.csv")
    assert download.status_code == 200
    assert "machine_id" in download.text

    traversal = client.get("/api/runs/op/reports/../../etc/passwd")
    assert traversal.status_code == 404


def test_static_shell_and_skins(client: TestClient) -> None:
    index = client.get("/")
    assert index.status_code == 200
    assert "FHOPS" in index.text
    assert "skin" in index.text
    assert client.get("/static/style.css").status_code == 200

    skins = client.get("/api/skins").json()
    assert {skin["id"] for skin in skins} >= {
        "operational-planner",
        "hauling-planner",
        "tactical-planner",
        "reviewer",
    }
    assert client.get("/api/skins/reviewer").json()["read_only"] is True
    assert client.get("/api/skins/nope").status_code == 404


def test_time_layers_and_map_for_all_domains(client: TestClient) -> None:
    op_time = client.get("/api/runs/op/time").json()
    assert op_time["domain"] == "operational"
    assert op_time["values"] == [1]
    assert op_time["shifts"] == ["DAY", "NIGHT"]

    op_layers = client.get("/api/runs/op/layers").json()
    names = {layer["name"]: layer for layer in op_layers["layers"]}
    assert names["blocks"]["available"] is True
    assert names["machines"]["available"] is True
    assert names["roads"]["available"] is False

    op_map = client.get("/api/runs/op/map?day=1&layers=blocks,machines,treatments").json()
    layers = {feature["properties"]["layer"] for feature in op_map["features"]}
    assert layers == {"blocks", "machines", "treatments"}
    machines = [f for f in op_map["features"] if f["properties"]["layer"] == "machines"]
    assert machines[0]["geometry"]["type"] == "Point"

    haul_time = client.get("/api/runs/haul/time").json()
    assert haul_time["domain"] == "hauling"
    assert haul_time["values"] == [1, 2]
    haul_map = client.get("/api/runs/haul/map?day=1&layers=blocks").json()
    b1 = next(f for f in haul_map["features"] if f["properties"]["block_id"] == "b1")
    assert b1["properties"]["flow_m3"] == 45.0

    tac_time = client.get("/api/runs/tac/time").json()
    assert tac_time["domain"] == "tactical_operational"
    assert tac_time["values"] == ["p1"]
    tac_map = client.get("/api/runs/tac/map?period=p1&layers=tactical_units").json()
    assert tac_map["features"][0]["properties"]["harvested_area_ha"] == 10.0


def test_unavailable_and_unknown_map_layers(client: TestClient) -> None:
    unavailable = client.get("/api/runs/op/map?layers=roads")
    assert unavailable.status_code == 400
    assert "unavailable" in unavailable.json()["detail"]
    unknown = client.get("/api/runs/op/map?layers=nope")
    assert unknown.status_code == 400
    assert "Unknown map layer" in unknown.json()["detail"]


def test_map_without_geometry_names_the_missing_source(tmp_path: Path) -> None:
    _operational_run(tmp_path)
    app = create_app(ServiceConfig(roots=[tmp_path], host="127.0.0.1"))
    client = TestClient(app)
    response = client.get("/api/runs/op/map")
    assert response.status_code == 404
    assert "geometry" in response.json()["detail"]


def test_remote_bind_is_refused_without_opt_in() -> None:
    assert is_loopback("127.0.0.1")
    assert is_loopback("localhost")
    assert not is_loopback("0.0.0.0")
    validate_bind("127.0.0.1", allow_remote=False)
    with pytest.raises(ValueError, match="non-loopback"):
        validate_bind("0.0.0.0", allow_remote=False)
    validate_bind("0.0.0.0", allow_remote=True)
    with pytest.raises(ValueError, match="non-loopback"):
        create_app(ServiceConfig(roots=[Path.cwd()], host="0.0.0.0"))
