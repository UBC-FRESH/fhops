"""Tree inventory registration and block-map tests (P17.2)."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.io import load_scenario
from fhops.tree_inventory import TreeInventoryError, load_tree_inventory
from fhops.tree_mapping import (
    TreeInventoryMappingError,
    TreeInventoryRegistrationError,
    map_tree_inventory,
    register_tree_inventory,
    write_tree_mapping,
)

runner = CliRunner()
REPO = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tree_inventory" / "synthetic_block"


def _inventory(tmp_path: Path, *, block_id: str = "B01") -> tuple[Path, Path]:
    root = tmp_path / "trees"
    root.mkdir()
    csv_path = root / "inventory.csv"
    source = (FIXTURE / "inventory.csv").read_text(encoding="utf-8")
    csv_path.write_text(source.replace("SYNTH_B01", block_id), encoding="utf-8")
    metadata = json.loads((FIXTURE / "inventory.meta.json").read_text(encoding="utf-8"))
    metadata["inventory_id"] = f"fixture-{block_id}"
    metadata["block_ids"] = [block_id]
    metadata["tree_count"] = 12
    metadata["inventory_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    metadata_path = root / "inventory.meta.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return csv_path, metadata_path


def _volume_proxy(csv_path: Path) -> float:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return sum(
        0.5 * (math.pi / 4.0) * (float(row["dbh_cm"]) / 100.0) ** 2 * float(row["height_m"])
        for row in rows
    )


def _scenario(tmp_path: Path, *, inventory: Path) -> Path:
    target = tmp_path / "tiny7"
    shutil.copytree(REPO / "examples" / "tiny7", target)
    proxy = _volume_proxy(inventory)
    blocks_path = target / "data" / "blocks.csv"
    with blocks_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    for row in rows:
        if row["id"] == "B01":
            row["work_required"] = f"{proxy:.6f}"
            row["volume_per_ha_m3"] = f"{proxy:.6f}"
            row["stem_density_per_ha"] = "12.0"
            row["avg_stem_size_m3"] = f"{proxy / 12.0:.6f}"
    with blocks_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return target / "scenario.yaml"


def test_register_pins_inventory_and_reloads(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)

    result = register_tree_inventory(scenario, inventory, metadata_path=metadata)
    assert result.written is True
    assert result.tree_count == 12
    assert result.block_ids == ("B01",)

    loaded = load_scenario(scenario)
    assert loaded.tree_inventory is not None
    pin = loaded.tree_inventory
    assert pin.inventory_id == "fixture-B01"
    assert pin.inventory_sha256 == result.inventory_sha256
    assert pin.metadata_sha256 == result.metadata_sha256
    assert pin.block_ids == ["B01"]
    assert pin.review_status == "reviewed"


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    before = scenario.read_text(encoding="utf-8")

    result = register_tree_inventory(scenario, inventory, metadata_path=metadata, dry_run=True)
    assert result.written is False
    assert scenario.read_text(encoding="utf-8") == before


def test_registration_is_idempotent(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    register_tree_inventory(scenario, inventory, metadata_path=metadata)
    register_tree_inventory(scenario, inventory, metadata_path=metadata)
    text = scenario.read_text(encoding="utf-8")
    assert text.count("\ntree_inventory:") == 1


def test_changed_inventory_is_rejected(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    register_tree_inventory(scenario, inventory, metadata_path=metadata)
    inventory.write_text(inventory.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    metadata_payload = json.loads(metadata.read_text(encoding="utf-8"))
    metadata_payload["inventory_sha256"] = hashlib.sha256(inventory.read_bytes()).hexdigest()
    metadata.write_text(json.dumps(metadata_payload, indent=2), encoding="utf-8")

    with pytest.raises(TreeInventoryRegistrationError, match="different tree inventory"):
        register_tree_inventory(scenario, inventory, metadata_path=metadata)


def test_crs_mismatch_is_rejected(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    scenario.write_text(
        scenario.read_text(encoding="utf-8") + "\ngeo_crs: EPSG:4326\n",
        encoding="utf-8",
    )

    with pytest.raises(TreeInventoryRegistrationError, match="CRS"):
        register_tree_inventory(scenario, inventory, metadata_path=metadata)


def test_unknown_block_is_rejected(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path, block_id="OTHER")
    scenario = _scenario(tmp_path, inventory=inventory)

    with pytest.raises(TreeInventoryRegistrationError, match="unknown block"):
        register_tree_inventory(scenario, inventory, metadata_path=metadata)


def test_map_reconciles_and_writes_manifest(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    register_tree_inventory(scenario, inventory, metadata_path=metadata)

    mapping = map_tree_inventory(scenario, generated_utc="2026-10-27T00:00:00+00:00")
    assert mapping.inventory_id == "fixture-B01"
    assert mapping.blocks[0].block_id == "B01"
    assert mapping.blocks[0].stem_density_status == "ok"
    assert mapping.blocks[0].volume_status == "ok"
    assert mapping.blocks_without_trees == ("B02",)
    assert "B02" in mapping.reconciliation["warning_blocks"]

    paths = write_tree_mapping(mapping, tmp_path / "map")
    assert paths["rows"].is_file()
    assert paths["manifest"].is_file()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "fhops.tree.inventory_map.v1"
    assert manifest["tree_count"] == 12
    assert manifest["blocks"][0]["block_id"] == "B01"


def test_map_refuses_without_pin(tmp_path: Path) -> None:
    inventory, _ = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)

    with pytest.raises(TreeInventoryMappingError, match="no tree_inventory pin"):
        map_tree_inventory(scenario)


def test_map_strict_refuses_reconciliation_warning(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    register_tree_inventory(scenario, inventory, metadata_path=metadata)

    with pytest.raises(TreeInventoryMappingError, match="reconciliation failed"):
        map_tree_inventory(scenario, require_reconciled=True)


def test_map_refuses_stale_inventory(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    register_tree_inventory(scenario, inventory, metadata_path=metadata)
    inventory.write_text(inventory.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(TreeInventoryError):
        load_tree_inventory(inventory, metadata_path=metadata, block_ids={"B01", "B02"})
    with pytest.raises(TreeInventoryMappingError):
        map_tree_inventory(scenario)


def test_cli_register_and_map(tmp_path: Path) -> None:
    inventory, metadata = _inventory(tmp_path)
    scenario = _scenario(tmp_path, inventory=inventory)
    out = tmp_path / "cli-map"

    registered = runner.invoke(
        app,
        [
            "tree",
            "register",
            str(scenario),
            str(inventory),
            "--metadata",
            str(metadata),
        ],
        prog_name="fhops",
    )
    assert registered.exit_code == 0, registered.output
    assert json.loads(registered.output)["written"] is True

    mapped = runner.invoke(
        app,
        ["tree", "map", str(scenario), "--out", str(out)],
        prog_name="fhops",
    )
    assert mapped.exit_code == 0, mapped.output
    payload = json.loads(mapped.output)
    assert payload["tree_count"] == 12
    assert (out / "tree_inventory_map.csv").is_file()
    assert (out / "tree_inventory_map.json").is_file()
