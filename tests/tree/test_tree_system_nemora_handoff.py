"""End-to-end test for the Nemora-generated tree-inventory fixture."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "nemora_handoff"


def test_nemora_inventory_validates_and_runs_tree_system(tmp_path: Path) -> None:
    scenario = EXAMPLE / "scenario" / "scenario.yaml"

    validation = runner.invoke(
        app,
        [
            "tree",
            "inventory",
            "validate",
            str(EXAMPLE / "tree_inventory" / "tree_inventory.csv"),
            "--metadata",
            str(EXAMPLE / "tree_inventory" / "tree_inventory.meta.json"),
            "--block",
            "B01",
        ],
        prog_name="fhops",
    )
    assert validation.exit_code == 0, validation.output
    assert json.loads(validation.output)["tree_count"] == 40

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
    assert payload["tree_count"] == 40
    assert payload["unreachable_count"] == 0
    assert payload["warnings"] == []
    assert (tmp_path / "system" / "system_events.json").is_file()
