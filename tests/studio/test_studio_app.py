"""API smoke tests for the Scenario Studio FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sandbox.studio.app import StudioConfig, create_app

ROOT = Path(__file__).resolve().parents[2]


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
