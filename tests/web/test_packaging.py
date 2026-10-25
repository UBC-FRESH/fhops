"""Packaging checks for the optional web extra and static assets."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("hatchling")

REPO = Path(__file__).resolve().parents[2]


def test_static_and_skin_sources_exist() -> None:
    for relative in (
        "src/fhops/web/static/index.html",
        "src/fhops/web/static/app.js",
        "src/fhops/web/static/style.css",
        "src/fhops/web/static/vendor/maplibre-gl.js",
        "src/fhops/web/static/vendor/maplibre-gl.css",
        "src/fhops/web/static/vendor/maplibre-gl.LICENSE.txt",
    ):
        assert (REPO / relative).is_file(), relative
    assert len(list((REPO / "src/fhops/web/skins").glob("*.json"))) == 4


def test_wheel_contains_web_assets_and_extra(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(REPO),
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(tmp_path),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    wheels = list(tmp_path.glob("fhops-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        for relative in (
            "fhops/web/static/index.html",
            "fhops/web/static/app.js",
            "fhops/web/static/style.css",
            "fhops/web/static/vendor/maplibre-gl.js",
            "fhops/web/static/vendor/maplibre-gl.css",
            "fhops/web/static/vendor/maplibre-gl.LICENSE.txt",
            "fhops/web/skins/operational-planner.json",
            "fhops/web/skins/hauling-planner.json",
            "fhops/web/skins/tactical-planner.json",
            "fhops/web/skins/reviewer.json",
        ):
            assert relative in names, relative
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
        assert "Provides-Extra: web" in metadata
        assert "fastapi" in metadata
        assert "uvicorn" in metadata
        assert "pyproj" in metadata
