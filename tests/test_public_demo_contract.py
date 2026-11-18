"""Public-demo contract tests.

These tests guard the deployed demo surface, not just the FHOPS library. The console is only
useful when it is served with a complete model instance: scenario, block geometry, domain
artifacts, KPIs, and map/result payloads. A future change that points the console at a
benchmark-only or partial run should fail here before it reaches the gateway.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo_app import ROOT, app

DEFAULT_MODEL_INSTANCE_ID = "gavin-full-estate"
MODEL_INSTANCES = {
    "gavin-full-estate": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "knife-structural": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "knife-gwm-policy": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "knife-gwm-lidar-policy": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "knife-lidar-clump-policy": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "gavin-optimized": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "gavin-policy": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "mkrf-full-estate": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "mkrf-low-estate": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "mkrf-high-estate": {
        "domain": "tactical_operational",
        "artifacts": {"harvest_decisions", "tactical_summary", "kpis", "summary"},
        "map_query": "period=P00",
    },
    "gavin-p00-operational": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
    "gavin-p01-operational": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
    "mkrf-p00-operational": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
    "mkrf-low-p00-operational": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
    "mkrf-high-p00-operational": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
    "mkrf-low-p01-haul-30d": {
        "domain": "hauling",
        "artifacts": {"haul_flows", "haul_schedule", "haul_summary", "haul_kpis"},
        "map_query": "day=1",
    },
    "mkrf-low-p01-operational": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
    "mkrf-high-p01-operational": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
    "mkrf-high-p01-haul-30d": {
        "domain": "hauling",
        "artifacts": {"haul_flows", "haul_schedule", "haul_summary", "haul_kpis"},
        "map_query": "day=1",
    },
    "mkrf-low-p01-haul-year": {
        "domain": "hauling",
        "artifacts": {"haul_flows", "haul_truckloads", "haul_summary", "haul_kpis"},
        "map_query": "day=1",
    },
    "knife-p00-operational": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
    "tfl6-lidar-demo": {
        "domain": "operational",
        "artifacts": {"assignments", "kpis", "day_summary", "shift_summary"},
        "map_query": "day=1",
    },
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
    for href in (
        "/fhops/",
        "/forests/",
        "/studio/",
        "/sandbox-v20261031i/",
        "/game",
    ):
        assert f'href="{href}"' in body
    assert "Experimental · classroom only" in body
    assert "/briefs/MKRF_EARLY_MANAGEMENT_PLAN.pdf" in body
    assert "/briefs/AFRF_EARLY_MANAGEMENT_PLAN.pdf" in body


def test_research_forest_portal_and_briefs(client: TestClient) -> None:
    response = client.get("/forests/")
    assert response.status_code == 200
    body = response.text
    for label in ("MKRF", "Gavin Lake", "Knife Creek"):
        assert label in body
    for path in (
        "/briefs/AFRF_EARLY_MANAGEMENT_PLAN.pdf",
        "/briefs/MKRF_EARLY_MANAGEMENT_PLAN.pdf",
        "/briefs/MKRF_RETENTION_AUDIT.pdf",
        "/flyovers/gavin_1032/optimal/viewer.html",
        "/flyovers/kc_57254551/optimal/viewer.html",
        "/stems/gavin_1032/trees.csv",
        "/stems/kc_57254551/trees.csv",
    ):
        assert client.get(path).status_code == 200, path
    assert 'id="briefs"' in body
    assert body.count("/briefs/") >= 4


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
    spec = MODEL_INSTANCES[run_id]
    assert record["domain"] == spec["domain"]
    files = record["files"]
    assert isinstance(files, dict)
    missing = set(spec["artifacts"]) - set(files)
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


@pytest.mark.parametrize("run_id", tuple(MODEL_INSTANCES))
def test_console_model_instance_has_scenario_geometry_and_results(
    client: TestClient, run_id: str
) -> None:
    record = _model_instance(client, run_id)
    _assert_complete_model_instance(record)
    spec = MODEL_INSTANCES[run_id]
    paths = [
        f"/api/scenarios/{run_id}",
        f"/api/runs/{run_id}/kpis",
        f"/api/runs/{run_id}/summary",
    ]
    if spec["domain"] == "tactical_operational":
        paths.append(f"/api/runs/{run_id}/tactical/harvest?period=P00")
    elif spec["domain"] == "hauling":
        paths.append(f"/api/runs/{run_id}/hauling/flows?day=1")
        if "haul_schedule" in record["files"]:
            paths.append(f"/api/runs/{run_id}/hauling/schedule")
    else:
        paths.extend(
            [
                f"/api/runs/{run_id}/playback?scope=day",
                f"/api/runs/{run_id}/lidar",
            ]
        )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.text}"

    map_response = client.get(f"/api/runs/{run_id}/map?{spec['map_query']}")
    assert map_response.status_code == 200, map_response.text
    payload = map_response.json()
    features = payload.get("features", [])
    assert features, "the console map must have features for the model instance"
    assert any(
        feature.get("properties", {}).get("layer") == "blocks"
        and feature.get("geometry") is not None
        for feature in features
    ), "the model instance must render block geometry, not an empty map"


def test_full_estate_covers_the_whole_forest(client: TestClient) -> None:
    _model_instance(client, "mkrf-full-estate")
    kpis = client.get("/api/runs/mkrf-full-estate/kpis").json()
    assert kpis["blocks_total"] >= 1_700
    assert kpis["blocks_scheduled"] >= 1_200
    assert kpis["total_production_m3"] > 3_000_000
    assert kpis["net_revenue_cad"] > 0
    map_payload = client.get("/api/runs/mkrf-full-estate/map?period=P00").json()
    block_features = [
        feature
        for feature in map_payload.get("features", [])
        if feature.get("properties", {}).get("layer") == "blocks"
    ]
    assert len(block_features) >= 1_700


def test_gavin_full_estate_covers_the_whole_forest(client: TestClient) -> None:
    _model_instance(client, "gavin-full-estate")
    kpis = client.get("/api/runs/gavin-full-estate/kpis").json()
    assert kpis["blocks_total"] >= 2_900
    assert kpis["blocks_scheduled"] >= 2_900
    assert kpis["total_production_m3"] > 5_000_000
    map_payload = client.get("/api/runs/gavin-full-estate/map?period=P00").json()
    block_features = [
        feature
        for feature in map_payload.get("features", [])
        if feature.get("properties", {}).get("layer") == "blocks"
    ]
    assert len(block_features) >= 2_900


def test_knife_structural_covers_the_whole_block(client: TestClient) -> None:
    _model_instance(client, "knife-structural")
    kpis = client.get("/api/runs/knife-structural/kpis").json()
    assert kpis["blocks_total"] >= 160
    assert kpis["blocks_scheduled"] >= 150
    assert kpis["total_production_m3"] > 0
    map_payload = client.get("/api/runs/knife-structural/map?period=P00").json()
    block_features = [
        feature
        for feature in map_payload.get("features", [])
        if feature.get("properties", {}).get("layer") == "blocks"
    ]
    assert len(block_features) >= 160


def test_knife_gwm_policy_uses_the_state_transition_library(client: TestClient) -> None:
    _model_instance(client, "knife-gwm-policy")
    kpis = client.get("/api/runs/knife-gwm-policy/kpis").json()
    assert kpis["blocks_total"] == 160
    assert kpis["blocks_scheduled"] == 157
    assert kpis["schedule_events"] == 1570
    assert kpis["total_production_m3"] > 2_400_000
    assert "sustained" in kpis["status_note"]
    production = client.get("/api/runs/knife-gwm-policy/tactical/production?limit=50").json()
    assert len(production["rows"]) == 30
    assert float(production["rows"][0]["volume_m3"]) > 0
    assert float(production["rows"][-1]["volume_m3"]) > 0
    map_payload = client.get("/api/runs/knife-gwm-policy/map?period=P00").json()
    block_features = [
        feature
        for feature in map_payload.get("features", [])
        if feature.get("properties", {}).get("layer") == "blocks"
    ]
    assert len(block_features) >= 160


def test_knife_gwm_lidar_policy_gates_on_lidar_harvest(client: TestClient) -> None:
    _model_instance(client, "knife-gwm-lidar-policy")
    kpis = client.get("/api/runs/knife-gwm-lidar-policy/kpis").json()
    assert kpis["blocks_total"] == 160
    assert kpis["blocks_scheduled"] == 135
    assert kpis["schedule_events"] == 1350
    assert kpis["total_production_m3"] > 2_300_000
    assert "LiDAR" in kpis["status_note"]
    production = client.get(
        "/api/runs/knife-gwm-lidar-policy/tactical/production?limit=50"
    ).json()
    assert len(production["rows"]) == 30
    assert float(production["rows"][-1]["volume_m3"]) > 0
    map_payload = client.get("/api/runs/knife-gwm-lidar-policy/map?period=P00").json()
    blocks = [
        feature
        for feature in map_payload.get("features", [])
        if feature.get("properties", {}).get("layer") == "blocks"
    ]
    assert len(blocks) == 160
    assert any("lidar_harvest_tph" in feature["properties"] for feature in blocks)


def test_knife_lidar_clump_policy_uses_spatial_clumps(client: TestClient) -> None:
    _model_instance(client, "knife-lidar-clump-policy")
    kpis = client.get("/api/runs/knife-lidar-clump-policy/kpis").json()
    assert kpis["blocks_total"] == 160
    assert kpis["blocks_scheduled"] == 132
    assert kpis["schedule_events"] == 624
    assert kpis["total_production_m3"] > 2_500_000
    assert "spatial-clump" in kpis["status_note"]
    production = client.get(
        "/api/runs/knife-lidar-clump-policy/tactical/production?limit=50"
    ).json()
    assert len(production["rows"]) == 30
    assert float(production["rows"][-1]["volume_m3"]) > 0


def test_gavin_optimized_draft_is_complete(client: TestClient) -> None:
    _model_instance(client, "gavin-optimized")
    kpis = client.get("/api/runs/gavin-optimized/kpis").json()
    assert kpis["blocks_total"] >= 2_900
    assert kpis["total_production_m3"] > 5_000_000
    assert kpis["targets_met"] + kpis["targets_below"] + kpis["targets_above"] == 61
    map_payload = client.get("/api/runs/gavin-optimized/map?period=P00").json()
    block_features = [
        feature
        for feature in map_payload.get("features", [])
        if feature.get("properties", {}).get("layer") == "blocks"
    ]
    assert len(block_features) >= 2_900


def test_afrf_finance_envelope_is_present_and_ordered(client: TestClient) -> None:
    for run_id in (
        "gavin-full-estate",
        "gavin-optimized",
        "gavin-policy",
        "knife-structural",
        "knife-gwm-policy",
        "knife-gwm-lidar-policy",
        "knife-lidar-clump-policy",
    ):
        kpis = client.get(f"/api/runs/{run_id}/kpis").json()
        low = kpis["finance_annual_net_revenue_cad_low"]
        base = kpis["finance_annual_net_revenue_cad_base"]
        high = kpis["finance_annual_net_revenue_cad_high"]
        assert 0 < low < base < high
        assert "not a budget forecast" in kpis["finance_basis"]


def test_gavin_policy_meets_all_public_targets(client: TestClient) -> None:
    _model_instance(client, "gavin-policy")
    kpis = client.get("/api/runs/gavin-policy/kpis").json()
    assert kpis["targets_met"] == 61
    assert kpis["targets_below"] == 0
    assert kpis["targets_above"] == 0
    assert kpis["incumbent_objective"] == 0.0
    assert kpis["total_production_m3"] > 5_000_000


def test_gavin_p00_operational_handoff(client: TestClient) -> None:
    _model_instance(client, "gavin-p00-operational")
    kpis = client.get("/api/runs/gavin-p00-operational/kpis").json()
    assert kpis["completed_blocks"] == 192
    assert kpis["remaining_work_total"] == 0
    assert kpis["total_production"] > 175_000
    assert kpis["makespan_day"] <= 365


def test_gavin_p01_operational_handoff(client: TestClient) -> None:
    _model_instance(client, "gavin-p01-operational")
    kpis = client.get("/api/runs/gavin-p01-operational/kpis").json()
    assert kpis["completed_blocks"] == 237
    assert kpis["remaining_work_total"] == 0
    assert kpis["total_production"] > 176_000
    assert kpis["makespan_day"] <= 365


def test_gavin_operational_runs_carry_road_haul_screen(client: TestClient) -> None:
    for run_id in ("gavin-p00-operational", "gavin-p01-operational"):
        kpis = client.get(f"/api/runs/{run_id}/kpis").json()
        assert kpis["haul_screen_avg_one_way_km"] > 0
        assert kpis["haul_screen_required_trucks"] >= 1
        assert kpis["haul_screen_loads_required"] > 0


def test_mkrf_scenario_set_is_complete(client: TestClient) -> None:
    rows = {}
    for run_id in ("mkrf-full-estate", "mkrf-low-estate", "mkrf-high-estate"):
        kpis = client.get(f"/api/runs/{run_id}/kpis").json()
        rows[run_id] = kpis
        assert kpis["blocks_total"] >= 1_700
        assert kpis["area_total_ha"] > 4_000
        assert kpis["net_revenue_cad"] > 0
        assert kpis["targets_met"] > 0
    assert rows["mkrf-full-estate"]["net_revenue_cad"] != rows["mkrf-low-estate"]["net_revenue_cad"]
    assert rows["mkrf-full-estate"]["net_revenue_cad"] != rows["mkrf-high-estate"]["net_revenue_cad"]


def test_mkrf_p00_operational_handoff(client: TestClient) -> None:
    _model_instance(client, "mkrf-p00-operational")
    kpis = client.get("/api/runs/mkrf-p00-operational/kpis").json()
    assert kpis["completed_blocks"] == 115
    assert kpis["remaining_work_total"] == 0
    assert kpis["total_production"] > 390_000
    assert kpis["makespan_day"] <= 365
    assert kpis["haul_screen_required_trucks"] >= 1


def test_mkrf_scenario_comparison_npv(client: TestClient) -> None:
    rows = {}
    for run_id in ("mkrf-full-estate", "mkrf-low-estate", "mkrf-high-estate"):
        kpis = client.get(f"/api/runs/{run_id}/kpis").json()
        rows[run_id] = kpis
        assert 0 < kpis["npv_net_6pct_cad"] < kpis["npv_net_4pct_cad"] < kpis["npv_net_2pct_cad"]
        assert kpis["annualized_net_after_cost_cad"] > 0
    assert rows["mkrf-low-estate"]["npv_net_2pct_cad"] > rows["mkrf-full-estate"]["npv_net_2pct_cad"]


def test_high_mkrf_p00_operational_handoff(client: TestClient) -> None:
    _model_instance(client, "mkrf-high-p00-operational")
    kpis = client.get("/api/runs/mkrf-high-p00-operational/kpis").json()
    assert kpis["completed_blocks"] == 78
    assert kpis["remaining_work_total"] == 0
    assert kpis["total_production"] > 298973
    assert kpis["makespan_day"] <= 365
    assert kpis["haul_screen_required_trucks"] >= 1


def test_mkrf_low_p01_haul_phase_i_ii(client: TestClient) -> None:
    _model_instance(client, "mkrf-low-p01-haul-30d")
    kpis = client.get("/api/runs/mkrf-low-p01-haul-30d/kpis").json()
    assert kpis["phase_i_delivered_m3"] > 49_000
    assert kpis["phase_i_truckloads"] >= 1_000
    assert kpis["loads"] > 0
    assert kpis["trucks_used"] > 0
    flows = client.get("/api/runs/mkrf-low-p01-haul-30d/hauling/flows?day=1").json()
    assert flows["total"] > 0


def test_mkrf_low_p01_operational_handoff(client: TestClient) -> None:
    _model_instance(client, "mkrf-low-p01-operational")
    kpis = client.get("/api/runs/mkrf-low-p01-operational/kpis").json()
    assert kpis["completed_blocks"] == 110
    assert kpis["remaining_work_total"] == 0
    assert kpis["total_production"] > 302769
    assert kpis["makespan_day"] <= 365
    assert kpis["haul_screen_required_trucks"] >= 1


def test_mkrf_high_p01_operational_handoff(client: TestClient) -> None:
    _model_instance(client, "mkrf-high-p01-operational")
    kpis = client.get("/api/runs/mkrf-high-p01-operational/kpis").json()
    assert kpis["completed_blocks"] == 112
    assert kpis["remaining_work_total"] == 0
    assert kpis["total_production"] > 307549
    assert kpis["makespan_day"] <= 365
    assert kpis["haul_screen_required_trucks"] >= 1


def test_mkrf_high_p01_haul_phase_i_ii(client: TestClient) -> None:
    _model_instance(client, "mkrf-high-p01-haul-30d")
    kpis = client.get("/api/runs/mkrf-high-p01-haul-30d/kpis").json()
    assert kpis["phase_i_delivered_m3"] > 49_000
    assert kpis["phase_i_truckloads"] >= 1_000
    assert kpis["loads"] > 0
    assert kpis["trucks_used"] > 0


def test_mkrf_low_p01_rolling_year_haul(client: TestClient) -> None:
    _model_instance(client, "mkrf-low-p01-haul-year")
    kpis = client.get("/api/runs/mkrf-low-p01-haul-year/kpis").json()
    assert kpis["phase_i_delivered_m3"] > 303_000
    assert kpis["phase_i_truckloads"] > 8_000
    assert kpis["months"] == 12
    assert kpis["phase_ii_months"] == 12
    assert kpis["phase_ii_loads"] > 0
    assert kpis["phase_ii_max_trucks"] > 0
    flows = client.get("/api/runs/mkrf-low-p01-haul-year/hauling/flows?day=1").json()
    assert flows["total"] > 0


def test_knife_p00_operational_handoff(client: TestClient) -> None:
    _model_instance(client, "knife-p00-operational")
    kpis = client.get("/api/runs/knife-p00-operational/kpis").json()
    assert kpis["completed_blocks"] == 50
    assert kpis["remaining_work_total"] == 0
    assert kpis["total_production"] > 158_000
    assert kpis["makespan_day"] <= 365
    assert kpis["haul_screen_required_trucks"] >= 1


def test_knife_structural_finance_screen(client: TestClient) -> None:
    kpis = client.get("/api/runs/knife-structural/kpis").json()
    assert kpis["finance_annual_net_revenue_cad_base"] > 0
    assert kpis["finance_npv_net_4pct_cad"] > 0
    assert kpis["finance_npv_net_6pct_cad"] < kpis["finance_npv_net_4pct_cad"]
