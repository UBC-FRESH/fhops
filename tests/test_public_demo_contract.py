"""Public-demo contract tests.

These tests guard the deployed demo surface, not just the FHOPS library. The console is only
useful when it is served with a complete model instance: scenario, assignments, block geometry,
KPIs, and playback artifacts. A future change that points the console at benchmark-only runs
should fail here before it reaches the gateway.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo_app import ROOT, app

DEFAULT_MODEL_INSTANCE_ID = "mkrf-cedar-flat"
MODEL_INSTANCE_IDS = ("mkrf-cedar-flat", "tfl6-lidar-demo")
REQUIRED_ARTIFACTS = {
    "assignments",
    "kpis",
    "day_summary",
    "shift_summary",
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _runs(client: TestClient) -> list[dict[str, object]]:
    response = client.get("/api/runs")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload, list) and payload
    return payload


def _model_instance(client: TestClient, run_id: str) -> dict[str, object]:
    runs = _runs(client)
    record = next((run for run in runs if run.get("run_id") == run_id), None)
    assert record is not None, f"{run_id} must remain discoverable: {runs}"
    return record


def test_gateway_keeps_every_demo_door(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.text
    for href in ("/fhops/", "/studio/", "/sandbox-v20261031i/", "/game"):
        assert f'href="{href}"' in body
    assert "Experimental · classroom only" in body


def test_full_console_shell_is_served_at_fhops(client: TestClient) -> None:
    response = client.get("/fhops/")
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    body = response.text
    assert 'src="/static/app.js' in body
    assert 'href="/static/style.css' in body
    assert 'href="static/' not in body


def _assert_complete_model_instance(record: dict[str, object]) -> None:
    run_id = str(record["run_id"])
    assert record["domain"] == "operational"
    files = record["files"]
    assert isinstance(files, dict)
    missing = REQUIRED_ARTIFACTS - set(files)
    assert not missing, f"{run_id} is missing {sorted(missing)}"

    manifest = record["manifest"]
    assert isinstance(manifest, dict)
    scenario = manifest.get("scenario")
    assert scenario, "run.json must name the scenario used by the console"
    scenario_path = (Path(record["path"]) / str(scenario)).resolve()
    assert scenario_path.is_file(), scenario_path
    assert scenario_path.is_relative_to(ROOT.resolve())


def test_console_run_has_a_complete_model_instance(client: TestClient) -> None:
    runs = _runs(client)
    assert runs[0]["run_id"] == DEFAULT_MODEL_INSTANCE_ID, (
        "the console selects runs[0] and must not open on a benchmark-only run"
    )
    _assert_complete_model_instance(_model_instance(client, DEFAULT_MODEL_INSTANCE_ID))


@pytest.mark.parametrize("run_id", MODEL_INSTANCE_IDS)
def test_console_model_instance_has_scenario_geometry_and_results(
    client: TestClient, run_id: str
) -> None:
    record = _model_instance(client, run_id)
    _assert_complete_model_instance(record)
    for path in (
        f"/api/scenarios/{run_id}",
        f"/api/runs/{run_id}/kpis",
        f"/api/runs/{run_id}/summary",
        f"/api/runs/{run_id}/playback?scope=day",
        f"/api/runs/{run_id}/lidar",
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.text}"

    map_response = client.get(f"/api/runs/{run_id}/map?day=1")
    assert map_response.status_code == 200, map_response.text
    payload = map_response.json()
    features = payload.get("features", [])
    assert features, "the console map must have features for the model instance"
    assert any(
        feature.get("properties", {}).get("layer") == "blocks"
        and feature.get("geometry") is not None
        for feature in features
    ), "the model instance must render block geometry, not an empty map"
