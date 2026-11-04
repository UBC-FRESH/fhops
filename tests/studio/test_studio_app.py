"""API smoke tests for the Scenario Studio FastAPI app."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sandbox.studio.app import StudioConfig, create_app
from sandbox.studio.projects import (
    create_project,
    project_edit_signature,
    save_project,
    terrain_signature,
)
from sandbox.tree_lab.cases import load_case

ROOT = Path(__file__).resolve().parents[2]


def test_run_history_marks_stale_after_project_edit(tmp_path: Path) -> None:
    """Run API records expose freshness and stale reasons."""
    projects_root = tmp_path / "projects"
    project = create_project(load_case(ROOT / "sandbox" / "cases" / "afrf-gavin"))
    saved = save_project(projects_root, project)
    project_id = saved["project_id"]
    run_id = "20261102T000000Z"
    run_dir = projects_root / project_id / "runs" / run_id
    run_dir.mkdir(parents=True)
    record = {
        "schema_version": "fhops.tree_lab.run.v1",
        "run_id": run_id,
        "status": "completed",
        "studio": {
            "edit_signature": project_edit_signature(saved),
            "terrain_signature": terrain_signature(saved),
            "project_revision": saved["revision"],
        },
    }
    (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    app = create_app(
        StudioConfig(cases_root=ROOT / "sandbox" / "cases", projects_root=projects_root)
    )
    client = TestClient(app)

    payload = client.get(f"/api/projects/{project_id}/runs").json()
    assert payload["runs"][0]["freshness"]["stale"] is False
    metadata = client.get(f"/api/projects/{project_id}/runs/{run_id}").json()
    assert metadata["freshness"]["stale"] is False
    assert metadata["run"]["run_id"] == run_id

    saved["retention"]["tree_ids"] = ["T00001"]
    save_project(projects_root, saved)
    payload = client.get(f"/api/projects/{project_id}/runs").json()
    freshness = payload["runs"][0]["freshness"]
    assert freshness["stale"] is True
    assert any("Project edits" in reason for reason in freshness["reasons"])


def test_compare_page_served(tmp_path: Path) -> None:
    """The comparison page is served without a project context."""
    app = create_app(
        StudioConfig(cases_root=ROOT / "sandbox" / "cases", projects_root=tmp_path / "projects")
    )
    response = TestClient(app).get("/compare")
    assert response.status_code == 200
    assert "Scenario comparison" in response.text


def test_stream_buffer_endpoint(tmp_path: Path) -> None:
    """The stream-buffer endpoint returns a closed riparian polygon."""
    app = create_app(
        StudioConfig(
            cases_root=ROOT / "sandbox" / "cases",
            projects_root=tmp_path / "projects",
        )
    )
    client = TestClient(app)
    response = client.post(
        "/api/geometry/stream-buffer",
        json={"points": [[0.0, 0.0], [0.0, 30.0]], "width_m": 20.0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["width_m"] == 20.0
    assert len(payload["polygon"]) == 4
    assert min(point[0] for point in payload["polygon"]) == -10.0
    assert max(point[0] for point in payload["polygon"]) == 10.0


def test_stream_buffer_endpoint_rejects_short_centreline(tmp_path: Path) -> None:
    """A single stream point is rejected with a client error."""
    app = create_app(
        StudioConfig(
            cases_root=ROOT / "sandbox" / "cases",
            projects_root=tmp_path / "projects",
        )
    )
    client = TestClient(app)
    response = client.post(
        "/api/geometry/stream-buffer",
        json={"points": [[0.0, 0.0]], "width_m": 20.0},
    )
    assert response.status_code == 400


def test_studio_page_exposes_run_comparison_launcher(tmp_path: Path) -> None:
    """The editor exposes a run pair selector that links to the compare page."""
    app = create_app(
        StudioConfig(cases_root=ROOT / "sandbox" / "cases", projects_root=tmp_path / "projects")
    )
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert 'id="compare-left-run"' in response.text
    assert 'id="compare-right-run"' in response.text
    assert 'id="open-compare"' in response.text


def test_salvage_preview_endpoint(tmp_path: Path) -> None:
    """The read-only salvage endpoint applies the packaged curve to project ages."""
    projects_root = tmp_path / "projects"
    saved = save_project(
        projects_root,
        create_project(load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")),
    )
    app = create_app(
        StudioConfig(cases_root=ROOT / "sandbox" / "cases", projects_root=projects_root)
    )
    client = TestClient(app)
    project_id = saved["project_id"]
    block_id = saved["block_id"]

    empty = client.post(f"/api/projects/{project_id}/salvage", json={"ages": {}})
    assert empty.status_code == 200
    assert empty.json()["configured"] is False

    response = client.post(
        f"/api/projects/{project_id}/salvage",
        json={"ages": {block_id: 2.0}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["curve"]["curve_id"] == "pnw_fire_killed_mixed_conifer"
    assert payload["rows"][0]["block_id"] == block_id
    assert payload["rows"][0]["retention_fraction"] == 0.89
    assert payload["rows"][0]["eligible_products"] == "lumber;pulp"

    invalid = client.post(
        f"/api/projects/{project_id}/salvage",
        json={"ages": {block_id: -1}},
    )
    assert invalid.status_code == 400
    assert "non-negative" in invalid.json()["detail"]

    unknown_curve = client.post(
        f"/api/projects/{project_id}/salvage",
        json={"ages": {block_id: 1.0}, "curve_id": "missing"},
    )
    assert unknown_curve.status_code == 400
    assert "unknown salvage decay curve" in unknown_curve.json()["detail"]
