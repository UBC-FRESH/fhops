"""End-to-end smoke test for the committed tree-system example."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "tree_system"


def test_tree_system_example_runs_and_exports_scene(tmp_path: Path) -> None:
    scenario = EXAMPLE / "scenario" / "scenario.yaml"
    assignments = EXAMPLE / "assignments.csv"

    system = runner.invoke(
        app,
        [
            "tree",
            "system",
            str(scenario),
            "--block",
            "B01",
            "--feller",
            "H1",
            "--skidder",
            "H2",
            "--skidder",
            "H3",
            "--processor",
            "H5",
            "--loader",
            "H4",
            "--shift-days",
            "2",
            "--shifts-per-day",
            "1",
            "--hours-per-shift",
            "8",
            "--truck-capacity",
            "5",
            "--truck-count",
            "1",
            "--landing-capacity",
            "15",
            "--out",
            str(tmp_path / "system"),
        ],
        prog_name="fhops",
    )
    assert system.exit_code == 0, system.output
    payload = json.loads(system.output)
    assert payload["tree_count"] == 12
    assert payload["processor_machine_id"] == "H5"
    assert (tmp_path / "system" / "system_events.json").is_file()

    scene = runner.invoke(
        app,
        [
            "tree",
            "scene",
            str(scenario),
            str(assignments),
            "--out",
            str(tmp_path / "scene"),
        ],
        prog_name="fhops",
    )
    assert scene.exit_code == 0, scene.output
    assert (tmp_path / "scene" / "scene.gltf").is_file()
    assert (tmp_path / "scene" / "scene.glb").is_file()

    for name in ("scene.gltf", "scene.glb", "system_events.json", "viewer.html"):
        assert (EXAMPLE / name).is_file()
