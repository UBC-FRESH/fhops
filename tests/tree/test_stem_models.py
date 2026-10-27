"""Stem volume and bucking tests (P17.3)."""

from __future__ import annotations

import csv
import dataclasses
import json
from pathlib import Path

import pytest
from test_inventory_mapping import _inventory, _scenario
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.stem import (
    ReferenceStemModel,
    StemModelError,
    build_stem_inventory,
    write_stem_inventory,
)
from fhops.tree_inventory import load_tree_inventory
from fhops.tree_mapping import register_tree_inventory

runner = CliRunner()
REPO = Path(__file__).resolve().parents[2]


def _fixture_tree():
    inventory = load_tree_inventory(
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "tree_inventory"
        / "synthetic_block"
        / "inventory.csv",
        block_ids={"SYNTH_B01"},
    )
    return inventory.rows[0]


def _stem_total(scenario: Path, inventory: Path, metadata: Path) -> float:
    loaded = load_tree_inventory(inventory, metadata_path=metadata, block_ids={"B01", "B02"})
    model = ReferenceStemModel()
    return sum(
        model.evaluate(row).merchantable_volume_m3 for row in loaded.rows if row.block_id == "B01"
    )


def _reconciled_scenario(tmp_path: Path) -> Path:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    total = _stem_total(scenario, inventory, metadata)
    blocks_path = scenario.parent / "data" / "blocks.csv"
    with blocks_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    for row in rows:
        if row["id"] == "B01":
            row["work_required"] = f"{total:.6f}"
            row["volume_per_ha_m3"] = f"{total:.6f}"
            row["stem_density_per_ha"] = "12.0"
            row["avg_stem_size_m3"] = f"{total / 12.0:.6f}"
        elif row["id"] == "B02":
            row["work_required"] = "0.0"
            row["volume_per_ha_m3"] = "0.0"
            row["stem_density_per_ha"] = "0.0"
    with blocks_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    register_tree_inventory(scenario, inventory, metadata_path=metadata)
    return scenario


def test_reference_model_volumes_and_logs() -> None:
    tree = _fixture_tree()
    model = ReferenceStemModel()
    result = model.evaluate(tree)

    assert result.tree_id == tree.tree_id
    assert result.gross_volume_m3 > result.merchantable_volume_m3 > 0
    assert result.logs
    assert sum(log.volume_m3 for log in result.logs) == pytest.approx(result.merchantable_volume_m3)
    assert all(log.product == "sawlog" for log in result.logs)
    assert all(log.length_m <= model.log_length_m for log in result.logs)


def test_pulp_threshold_and_custom_log_length() -> None:
    tree = _fixture_tree()
    small = dataclasses.replace(tree, dbh_cm=15.0)
    model = ReferenceStemModel(log_length_m=2.5)

    result = model.evaluate(small)
    assert all(log.product == "pulp" for log in result.logs)
    assert all(log.length_m <= 2.5 for log in result.logs)
    assert sum(log.volume_m3 for log in result.logs) == pytest.approx(result.merchantable_volume_m3)


def test_invalid_geometry_is_rejected() -> None:
    tree = _fixture_tree()
    with pytest.raises(StemModelError, match="invalid DBH"):
        ReferenceStemModel().evaluate(dataclasses.replace(tree, dbh_cm=0.0))
    with pytest.raises(StemModelError, match="invalid height"):
        ReferenceStemModel().evaluate(dataclasses.replace(tree, height_m=0.0))
    with pytest.raises(StemModelError, match="merchantable height"):
        ReferenceStemModel().evaluate(
            dataclasses.replace(tree, merchantable_height_m=tree.height_m + 1.0)
        )


def test_build_stem_inventory_reconciles(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    stem = build_stem_inventory(scenario, generated_utc="2026-10-27T00:00:00+00:00")

    assert stem.trees
    assert stem.blocks[0].block_id == "B01"
    assert stem.blocks[0].volume_status == "ok"
    assert stem.blocks[0].log_count >= stem.blocks[0].tree_count
    assert stem.to_dict()["merchantable_volume_m3"] > 0

    paths = write_stem_inventory(stem, tmp_path / "stems")
    assert paths["logs"].is_file()
    assert paths["blocks"].is_file()
    assert paths["manifest"].is_file()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "fhops.tree.stems.v1"
    assert manifest["blocks"][0]["block_id"] == "B01"


def test_strict_volume_reconciliation_refuses(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    register_tree_inventory(scenario, inventory, metadata_path=metadata)

    with pytest.raises(StemModelError, match="reconciliation failed"):
        build_stem_inventory(scenario, require_reconciled=True)


def test_cli_stems_writes_outputs(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    out = tmp_path / "cli-stems"

    result = runner.invoke(
        app,
        ["tree", "stems", str(scenario), "--out", str(out)],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tree_count"] == 12
    assert (out / "tree_stems.csv").is_file()
    assert (out / "tree_stem_blocks.csv").is_file()
    assert (out / "tree_stems.json").is_file()


def test_cli_stems_rejects_invalid_model_option(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    result = runner.invoke(
        app,
        ["tree", "stems", str(scenario), "--form-factor", "0"],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "form_factor" in result.output
