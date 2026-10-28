"""Individual-tree inventory contract tests (P17.1)."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.tree_inventory import (
    TREE_INVENTORY_REQUIRED_COLUMNS,
    TreeInventoryError,
    load_tree_inventory,
    validate_tree_inventory,
)

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tree_inventory" / "synthetic_block"


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "tree_id": "ST001",
        "block_id": "SYNTH_B01",
        "x_m": 881712.0,
        "y_m": 627512.0,
        "elevation_m": 412.0,
        "species_code": "Fd",
        "dbh_cm": 28.0,
        "height_m": 22.0,
        "crown_radius_m": 2.4,
        "status": "live",
        "confidence": 0.94,
        "source_id": "synthetic",
        "source_tile_id": "T01",
        "merchantable_height_m": "",
        "defect": "",
        "grade_hint": "",
    }
    row.update(overrides)
    return row


def _metadata(csv_path: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "fhops.tree.inventory.v1",
        "inventory_id": "test-inventory",
        "generated_utc": "2026-10-27T00:00:00+00:00",
        "source_id": "synthetic",
        "producer": "test",
        "method": "synthetic",
        "crs": "EPSG:3005",
        "units": {
            "x_y": "m",
            "elevation": "m",
            "dbh": "cm",
            "height": "m",
            "crown_radius": "m",
        },
        "review_status": "reviewed",
        "reviewed_by": "reviewer",
        "block_ids": ["SYNTH_B01"],
        "caveats": ["Synthetic test inventory."],
        "tree_count": 1,
        "inventory_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }
    payload.update(overrides)
    return payload


def _write_inventory(
    tmp_path: Path,
    rows: list[dict[str, object]],
    *,
    columns: tuple[str, ...] = (
        *TREE_INVENTORY_REQUIRED_COLUMNS,
        "elevation_m",
        "crown_radius_m",
        "source_id",
        "source_tile_id",
        "merchantable_height_m",
        "defect",
        "grade_hint",
    ),
    metadata: dict[str, object] | None = None,
    write_metadata: bool = True,
) -> tuple[Path, Path]:
    csv_path = tmp_path / "inventory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    metadata_path = tmp_path / "inventory.meta.json"
    if write_metadata:
        payload = _metadata(csv_path) if metadata is None else metadata
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return csv_path, metadata_path


def test_valid_fixture_loads() -> None:
    inventory = load_tree_inventory(
        FIXTURE / "inventory.csv",
        block_ids={"SYNTH_B01"},
    )

    assert len(inventory.rows) == 12
    assert inventory.metadata.review_status == "reviewed"
    assert inventory.rows[0].species_code == "Fd"
    assert inventory.rows[0].tree_id == "ST001"
    assert inventory.sha256
    assert inventory.to_dict()["tree_count"] == 12


def test_cli_validates_fixture() -> None:
    result = runner.invoke(
        app,
        [
            "tree",
            "inventory",
            "validate",
            str(FIXTURE / "inventory.csv"),
            "--block",
            "SYNTH_B01",
        ],
        prog_name="fhops",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["is_valid"] is True
    assert payload["tree_count"] == 12


def test_duplicate_tree_id_is_rejected(tmp_path: Path) -> None:
    path, _ = _write_inventory(
        tmp_path,
        [_row(), _row()],
    )

    with pytest.raises(TreeInventoryError, match="Duplicate tree_id"):
        load_tree_inventory(path)


def test_unknown_block_is_rejected(tmp_path: Path) -> None:
    path, _ = _write_inventory(tmp_path, [_row(block_id="OTHER")])

    report = validate_tree_inventory(path, block_ids={"SYNTH_B01"})
    assert report.is_valid is False
    assert any("unknown block" in error for error in report.errors)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("dbh_cm", -1.0, "dbh_cm must be positive"),
        ("height_m", 0.0, "height_m must be positive"),
        ("height_m", math.nan, "height_m must be a finite number"),
        ("confidence", 1.2, "confidence must be within"),
        ("crown_radius_m", -2.0, "crown_radius_m must be positive"),
        ("merchantable_height_m", 25.0, "exceeds height_m"),
    ],
)
def test_invalid_tree_values_are_rejected(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    path, _ = _write_inventory(tmp_path, [_row(**{field: value})])

    report = validate_tree_inventory(path)
    assert report.is_valid is False
    assert any(message in error for error in report.errors)


def test_missing_required_column_is_rejected(tmp_path: Path) -> None:
    columns = tuple(
        column for column in TREE_INVENTORY_REQUIRED_COLUMNS if column != "species_code"
    )
    path, _ = _write_inventory(tmp_path, [_row()], columns=columns)

    report = validate_tree_inventory(path)
    assert report.is_valid is False
    assert any("missing required columns" in error for error in report.errors)


def test_metadata_errors_are_rejected(tmp_path: Path) -> None:
    path, metadata_path = _write_inventory(tmp_path, [_row()])
    payload = _metadata(path, review_status="reviewed", reviewed_by=None)
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_tree_inventory(path)
    assert report.is_valid is False
    assert any("reviewed_by" in error for error in report.errors)

    path, metadata_path = _write_inventory(
        tmp_path,
        [_row()],
        metadata=_metadata(path, schema_version="fhops.tree.inventory.v2"),
    )
    report = validate_tree_inventory(path)
    assert report.is_valid is False
    assert any("Unsupported tree inventory schema" in error for error in report.errors)

    path, metadata_path = _write_inventory(
        tmp_path,
        [_row()],
        metadata=_metadata(path, inventory_sha256="0" * 64),
    )
    report = validate_tree_inventory(path)
    assert report.is_valid is False
    assert any("does not match the CSV" in error for error in report.errors)


def test_missing_metadata_is_rejected(tmp_path: Path) -> None:
    path, _ = _write_inventory(tmp_path, [_row()], write_metadata=False)

    report = validate_tree_inventory(path)
    assert report.is_valid is False
    assert any("metadata" in error for error in report.errors)


def test_cli_invalid_exit_code(tmp_path: Path) -> None:
    path, _ = _write_inventory(tmp_path, [_row(block_id="OTHER")])

    result = runner.invoke(
        app,
        ["tree", "inventory", "validate", str(path), "--block", "SYNTH_B01"],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["is_valid"] is False
