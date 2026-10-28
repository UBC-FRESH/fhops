"""End-to-end P17 tree-scale workflow on the committed synthetic fixture."""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tree_scale"


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "tree_scale"
    shutil.copytree(FIXTURE, target)
    return target


def _run(*args: str) -> dict[str, object]:
    result = runner.invoke(app, list(args), prog_name="fhops")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_tree_scale_fixture_end_to_end(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    scenario = root / "scenario" / "scenario.yaml"
    inventory = root / "tree_inventory" / "inventory.csv"
    metadata = root / "tree_inventory" / "inventory.meta.json"
    assignments = root / "assignments.csv"

    validation = _run(
        "tree",
        "inventory",
        "validate",
        str(inventory),
        "--metadata",
        str(metadata),
        "--block",
        "B01",
    )
    assert validation["is_valid"] is True
    assert validation["tree_count"] == 12

    registration = _run(
        "tree",
        "register",
        str(scenario),
        str(inventory),
        "--metadata",
        str(metadata),
    )
    assert registration["inventory_id"] == "tree-scale-fixture-B01"

    mapping = _run("tree", "map", str(scenario), "--out", str(root / "map"))
    assert mapping["blocks"][0]["tree_count"] == 12
    assert mapping["blocks"][0]["volume_status"] != "warning"

    stems = _run("tree", "stems", str(scenario), "--out", str(root / "stems"))
    assert stems["tree_count"] == 12
    assert stems["blocks"][0]["volume_status"] != "warning"

    simulation = _run(
        "tree",
        "simulate",
        str(scenario),
        "--block",
        "B01",
        "--machine",
        "H1",
        "--out",
        str(root / "simulate"),
    )
    assert simulation["processed_count"] == 12
    assert simulation["unreachable_count"] == 0

    replay = _run(
        "tree",
        "replay",
        str(scenario),
        str(assignments),
        "--out",
        str(root / "replay"),
    )
    assert replay["processed_count"] == 12
    assert not replay["discrepancies"]

    scene = _run(
        "tree",
        "scene",
        str(scenario),
        str(assignments),
        "--out",
        str(root / "scene"),
    )
    assert scene["tree_count"] == 12
    assert scene["processed_count"] == 12
    assert scene["log_count"] == 68

    for output in (
        root / "map" / "tree_inventory_map.json",
        root / "stems" / "tree_stems.json",
        root / "simulate" / "tree_machine_simulation.json",
        root / "replay" / "tree_replay.json",
        root / "scene" / "scene.gltf",
        root / "scene" / "scene.glb",
        root / "scene" / "scene_manifest.json",
    ):
        assert output.is_file()

    glb = (root / "scene" / "scene.glb").read_bytes()
    magic, version, length = struct.unpack_from("<III", glb, 0)
    assert magic == 0x46546C67
    assert version == 2
    assert length == len(glb)
