"""Static regression checks for the web shell foundation."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from fhops.web.app import ServiceConfig, create_app


def _client(tmp_path: Path) -> TestClient:
    app = create_app(ServiceConfig(roots=[tmp_path / "runs"], workspace=tmp_path))
    return TestClient(app)


def test_shell_has_workspaces_loading_and_accessible_tabs(tmp_path: Path) -> None:
    client = _client(tmp_path)
    html = client.get("/").text
    assert 'id="workspaces"' in html
    assert 'role="tablist"' in html
    assert 'id="panel-loading"' in html
    assert 'id="app-loading"' in html
    assert "app.js?v=13" in html


def test_shell_script_has_url_and_tab_behavior(tmp_path: Path) -> None:
    client = _client(tmp_path)
    script = client.get("/static/app.js?v=13").text
    assert "WORKSPACE_DEFS" in script
    assert "history.pushState" in script
    assert "wireTabKeyboard" in script
    assert "aria-selected" in script
    assert "applyURLState" in script
    assert "sort-button" in script
    assert "selected-block-line" in script
    assert "MAP_COLORS" in script
    assert 'state.panel === "map"' in script


def test_shell_css_has_responsive_rules(tmp_path: Path) -> None:
    client = _client(tmp_path)
    css = client.get("/static/style.css").text
    assert ".workspaces" in css
    assert ".workspace-tab" in css
    assert "@media (max-width: 1200px)" in css
    assert ".app-loading" in css
    assert ".panel-loading" in css
