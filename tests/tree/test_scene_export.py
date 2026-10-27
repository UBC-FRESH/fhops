"""Tree scene export tests (P17.6)."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from test_stem_models import _reconciled_scenario
from test_tree_replay import _assignments, _stem_total, _valid_rows
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.tree_scene import write_tree_scene

runner = CliRunner()


def _scene_inputs(tmp_path: Path) -> tuple[Path, Path]:
    scenario = _reconciled_scenario(tmp_path)
    assignments = _assignments(tmp_path / "assignments.csv", _valid_rows(_stem_total(scenario)))
    return scenario, assignments


def test_scene_exports_gltf_glb_and_manifest(tmp_path: Path) -> None:
    scenario, assignments = _scene_inputs(tmp_path)
    result = write_tree_scene(scenario, assignments, tmp_path / "scene")

    assert result.tree_count == 12
    assert result.processed_count == 12
    assert result.log_count > 0
    assert result.lod == "detailed"
    for path in (
        result.gltf_path,
        result.glb_path,
        result.manifest_path,
        result.camera_path,
        result.viewer_path,
    ):
        assert path.is_file()

    gltf = json.loads(result.gltf_path.read_text(encoding="utf-8"))
    assert gltf["asset"]["version"] == "2.0"
    assert gltf["scenes"][0]["nodes"]
    assert gltf["buffers"][0]["uri"].startswith("data:application/octet-stream;base64,")
    tree_nodes = [node for node in gltf["nodes"] if node["name"].startswith("tree:")]
    assert len(tree_nodes) == 12
    assert any(node["name"] == "machine_path" for node in gltf["nodes"])

    glb = result.glb_path.read_bytes()
    magic, version, length = struct.unpack_from("<III", glb, 0)
    assert magic == 0x46546C67
    assert version == 2
    assert length == len(glb)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "fhops.tree.scene.v1"
    assert manifest["tree_count"] == 12
    assert manifest["processed_count"] == 12
    assert manifest["lod"] == "detailed"
    assert manifest["files"]["glb"] == "scene.glb"

    camera = json.loads(result.camera_path.read_text(encoding="utf-8"))
    assert len(camera["frames"]) == 4
    assert "GLTFLoader" in result.viewer_path.read_text(encoding="utf-8")


def test_scene_export_is_deterministic(tmp_path: Path) -> None:
    scenario, assignments = _scene_inputs(tmp_path)
    first = write_tree_scene(scenario, assignments, tmp_path / "first")
    second = write_tree_scene(scenario, assignments, tmp_path / "second")

    assert first.scene_id == second.scene_id
    assert first.gltf_path.read_bytes() == second.gltf_path.read_bytes()
    assert first.glb_path.read_bytes() == second.glb_path.read_bytes()
    assert first.camera_path.read_bytes() == second.camera_path.read_bytes()


def test_simple_lod_and_log_cap(tmp_path: Path) -> None:
    scenario, assignments = _scene_inputs(tmp_path)
    result = write_tree_scene(
        scenario,
        assignments,
        tmp_path / "scene",
        lod_threshold=1,
        max_log_nodes=0,
    )

    assert result.lod == "simple"
    assert result.log_count == 0
    gltf = json.loads(result.gltf_path.read_text(encoding="utf-8"))
    assert not any(node["name"].startswith("log:") for node in gltf["nodes"])


def test_cli_scene_writes_outputs(tmp_path: Path) -> None:
    scenario, assignments = _scene_inputs(tmp_path)
    out = tmp_path / "cli-scene"

    result = runner.invoke(
        app,
        ["tree", "scene", str(scenario), str(assignments), "--out", str(out)],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tree_count"] == 12
    assert payload["lod"] == "detailed"
    assert (out / "scene.gltf").is_file()
    assert (out / "scene.glb").is_file()
