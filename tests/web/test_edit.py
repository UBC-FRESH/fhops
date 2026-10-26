"""Scenario editing API tests: loader round-trip, comments, and overlays."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from fhops.scenario.io import load_scenario
from fhops.web.app import ServiceConfig, create_app


def _app_client(tmp_path: Path, *, allow_agent: bool = False) -> TestClient:
    app = create_app(
        ServiceConfig(
            roots=[tmp_path / "runs"],
            workspace=tmp_path,
            allow_agent=allow_agent,
            agent_command=(sys.executable, "-c", "print('{}')"),
        )
    )
    return TestClient(app)


def _register_run(tmp_path: Path, run_id: str, domain: str, scenario: Path) -> None:
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "run_id": run_id,
                "domain": domain,
                "run_type": "test",
                "status": "ok",
                "scenario": str(scenario),
            }
        ),
        encoding="utf-8",
    )


def _copy_tiny7(tmp_path: Path) -> Path:
    target = tmp_path / "tiny7"
    shutil.copytree(Path("examples/tiny7"), target)
    scenario = target / "scenario.yaml"
    scenario.write_text(
        "# operator comment: keep me\n" + scenario.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return scenario


def test_objective_round_trip_preserves_comments(tmp_path: Path) -> None:
    scenario = _copy_tiny7(tmp_path)
    _register_run(tmp_path, "run-a", "operational", scenario)
    client = _app_client(tmp_path)

    detail = client.get("/api/scenarios/run-a")
    assert detail.status_code == 200, detail.text
    assert detail.json()["objective_weights"]["mobilisation"] == 0.5

    response = client.put(
        "/api/scenarios/run-a/objective",
        json={"weights": {"production": 1.3, "mobilisation": 0.7, "transitions": 0.2}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["objective_weights"]["production"] == 1.3
    assert "# operator comment: keep me" in scenario.read_text(encoding="utf-8")
    loaded = load_scenario(scenario)
    assert loaded.objective_weights is not None
    assert loaded.objective_weights.transitions == 0.2


def test_invalid_objective_is_refused_without_writing(tmp_path: Path) -> None:
    scenario = _copy_tiny7(tmp_path)
    _register_run(tmp_path, "run-a", "operational", scenario)
    client = _app_client(tmp_path)
    before = scenario.read_text(encoding="utf-8")
    response = client.put(
        "/api/scenarios/run-a/objective",
        json={"weights": {"production": -1.0}},
    )
    assert response.status_code == 400
    assert "non-negative" in response.json()["detail"].lower()
    assert scenario.read_text(encoding="utf-8") == before


def test_locks_round_trip_and_rejection(tmp_path: Path) -> None:
    scenario = _copy_tiny7(tmp_path)
    _register_run(tmp_path, "run-a", "operational", scenario)
    client = _app_client(tmp_path)
    response = client.put(
        "/api/scenarios/run-a/locks",
        json={"locks": [{"machine_id": "H1", "block_id": "B01", "day": 1}]},
    )
    assert response.status_code == 200, response.text
    loaded = load_scenario(scenario)
    assert loaded.locked_assignments is not None
    assert loaded.locked_assignments[0].block_id == "B01"

    bad = client.put(
        "/api/scenarios/run-a/locks",
        json={"locks": [{"machine_id": "H1", "block_id": "B01", "day": 99}]},
    )
    assert bad.status_code == 400
    assert "day" in bad.json()["detail"].lower()


def test_lock_edit_twice_does_not_duplicate_section(tmp_path: Path) -> None:
    scenario = _copy_tiny7(tmp_path)
    _register_run(tmp_path, "run-a", "operational", scenario)
    client = _app_client(tmp_path)
    payload = {"locks": [{"machine_id": "H1", "block_id": "B01", "day": 1}]}
    assert client.put("/api/scenarios/run-a/locks", json=payload).status_code == 200
    assert client.put("/api/scenarios/run-a/locks", json=payload).status_code == 200
    loaded = load_scenario(scenario)
    assert loaded.locked_assignments is not None
    assert len(loaded.locked_assignments) == 1


def test_hauling_edit_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "hauling"
    shutil.copytree(Path("examples/hauling"), target)
    scenario = target / "scenario.yaml"
    _register_run(tmp_path, "run-h", "hauling", scenario)
    client = _app_client(tmp_path)
    response = client.put(
        "/api/scenarios/run-h/hauling",
        json={
            "driver_policy": {"regular_minutes": 480.0, "max_overtime_minutes": 120.0},
            "contractors": [{"id": "c1", "preferred_daily_truckloads": 6.0}],
        },
    )
    assert response.status_code == 200, response.text
    loaded = load_scenario(scenario)
    assert loaded.hauling is not None
    assert loaded.hauling.driver_policy.regular_minutes == 480.0
    contractor = next(item for item in loaded.hauling.contractors if item.id == "c1")
    assert contractor.preferred_daily_truckloads == 6.0

    bad = client.put(
        "/api/scenarios/run-h/hauling",
        json={"contractors": [{"id": "c1", "preferred_daily_truckloads": -2.0}]},
    )
    assert bad.status_code == 400


def test_tactical_overlay_is_separate_and_validated(tmp_path: Path) -> None:
    scenario = tmp_path / "tactical.yaml"
    shutil.copy2(
        Path("tests/fixtures/tactical_operational/practitioner-case/scenario.yaml"), scenario
    )
    _register_run(tmp_path, "run-t", "tactical_operational", scenario)
    client = _app_client(tmp_path)
    before = scenario.read_text(encoding="utf-8")
    detail = client.get("/api/scenarios/run-t")
    assert detail.status_code == 200, detail.text
    assert detail.json()["tactical"]["facility_demand"]

    response = client.put(
        "/api/scenarios/run-t/tactical",
        json={
            "overlay": {
                "overlay_id": "web-test",
                "facility_demand": [
                    {
                        "facility_id": "coastal_sawmill",
                        "product_id": "sawlog",
                        "period_id": "Y2027-P01",
                        "target_m3": 2300.0,
                    }
                ],
            }
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()["tactical"]
    assert Path(payload["overlay_path"]).is_file()
    assert Path(payload["derived_path"]).is_file()
    row = next(
        item
        for item in payload["facility_demand"]
        if item["facility_id"] == "coastal_sawmill" and item["period_id"] == "Y2027-P01"
    )
    assert row["target_m3"] == 2300.0
    assert scenario.read_text(encoding="utf-8") == before

    bad = client.put(
        "/api/scenarios/run-t/tactical",
        json={"overlay": {"facility_demand": [{"facility_id": "missing", "product_id": "x"}]}},
    )
    assert bad.status_code == 400
    assert scenario.read_text(encoding="utf-8") == before


def test_scenario_path_outside_roots_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-scenario.yaml"
    outside.write_text("name: outside\n", encoding="utf-8")
    _register_run(tmp_path, "run-x", "operational", outside)
    client = _app_client(tmp_path)
    response = client.get("/api/scenarios/run-x")
    assert response.status_code == 403
