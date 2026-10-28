"""Fail-closed checks for the end-to-end tree-scale workflow."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tree_scale"


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "tree_scale"
    shutil.copytree(FIXTURE, target)
    return target


def _invoke(*args: str):
    return runner.invoke(app, list(args), prog_name="fhops")


def _register(root: Path) -> None:
    result = _invoke(
        "tree",
        "register",
        str(root / "scenario" / "scenario.yaml"),
        str(root / "tree_inventory" / "inventory.csv"),
        "--metadata",
        str(root / "tree_inventory" / "inventory.meta.json"),
    )
    assert result.exit_code == 0, result.output


def test_map_requires_a_pin(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    result = _invoke(
        "tree", "map", str(root / "scenario" / "scenario.yaml"), "--out", str(root / "map")
    )
    assert result.exit_code == 1
    assert "no tree_inventory pin" in result.stderr
    assert not (root / "map").exists()


def test_register_rejects_unknown_block(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    for name in ("blocks.csv", "prod_rates.csv"):
        path = root / "scenario" / "data" / name
        path.write_text(path.read_text(encoding="utf-8").replace("B01", "B02"), encoding="utf-8")
    result = _invoke(
        "tree",
        "register",
        str(root / "scenario" / "scenario.yaml"),
        str(root / "tree_inventory" / "inventory.csv"),
        "--metadata",
        str(root / "tree_inventory" / "inventory.meta.json"),
    )
    assert result.exit_code == 1
    assert "unknown block" in result.stderr
    assert "tree_inventory" not in (root / "scenario" / "scenario.yaml").read_text(encoding="utf-8")


def test_stale_inventory_checksum_fails_validation(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    metadata = root / "tree_inventory" / "inventory.meta.json"
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["inventory_sha256"] = "0" * 64
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    result = _invoke(
        "tree",
        "inventory",
        "validate",
        str(root / "tree_inventory" / "inventory.csv"),
        "--metadata",
        str(metadata),
        "--block",
        "B01",
    )
    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["is_valid"] is False
    assert any("inventory_sha256" in error for error in report["errors"])


def test_strict_stem_reconciliation_fails(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    _register(root)
    out = root / "stems"
    result = _invoke(
        "tree",
        "stems",
        str(root / "scenario" / "scenario.yaml"),
        "--strict",
        "--form-factor",
        "0.9",
        "--out",
        str(out),
    )
    assert result.exit_code == 1
    assert "reconciliation failed" in result.stderr.lower()
    assert not out.exists()


def test_strict_replay_shortfall_fails(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    _register(root)
    assignments = root / "assignments.csv"
    assignments.write_text(
        "machine_id,block_id,day,shift_id,assigned,production\nH1,B01,1,S1,1,100\n",
        encoding="utf-8",
    )
    out = root / "replay"
    result = _invoke(
        "tree",
        "replay",
        str(root / "scenario" / "scenario.yaml"),
        str(assignments),
        "--strict",
        "--out",
        str(out),
    )
    assert result.exit_code == 1
    assert "replay is incomplete" in result.stderr.lower()
    assert not out.exists()
