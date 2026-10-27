"""FEMIC hydrology crosswalk mapping tests (P15.3)."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.hydrology_mapping import (
    FemicHydrologyMappingError,
    load_hydrology_crosswalk,
    map_femic_hydrology_to_scenario,
    write_hydrology_mapping,
)
from fhops.scenario.hydrology_registration import register_femic_hydrology_bundle
from fhops.scenario.io import load_scenario

runner = CliRunner()
REPO = Path(__file__).resolve().parents[2]
BUNDLE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "response"
SCENARIO = REPO / "examples" / "lidar_tfl6" / "scenario.yaml"


def _scenario(tmp_path: Path, *, register: bool = True) -> Path:
    target = tmp_path / "lidar_tfl6"
    shutil.copytree(SCENARIO.parent, target)
    scenario = target / "scenario.yaml"
    if register:
        register_femic_hydrology_bundle(scenario, BUNDLE)
    return scenario


def _rows(scenario_path: Path) -> list[dict[str, object]]:
    scenario = load_scenario(scenario_path)
    rows: list[dict[str, object]] = []
    for block_id in scenario.block_ids():
        rows.append(_row(block_id=block_id))
    for landing_id in scenario.landing_ids():
        rows.append(_row(landing_id=landing_id))
    for road in scenario.road_construction or []:
        rows.append(_row(road_id=road.id))
    return rows


def _row(
    *,
    block_id: str | None = None,
    landing_id: str | None = None,
    road_id: str | None = None,
    unit_id: str = "unit-1",
    watershed_id: str = "watershed-1",
    receptor_id: str | None = "receptor-1",
) -> dict[str, object]:
    return {
        "block_id": block_id or "",
        "landing_id": landing_id or "",
        "road_id": road_id or "",
        "unit_id": unit_id,
        "watershed_id": watershed_id,
        "receptor_id": receptor_id or "",
        "notes": "Synthetic crosswalk row.",
    }


def _write_crosswalk(path: Path, rows: list[dict[str, object]]) -> Path:
    columns = (
        "block_id",
        "landing_id",
        "road_id",
        "unit_id",
        "watershed_id",
        "receptor_id",
        "notes",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_metadata(
    path: Path,
    *,
    crosswalk_sha256: str | None = None,
    review_status: str = "reviewed",
    reviewed_by: str | None = "reviewer-1",
) -> Path:
    payload = {
        "schema_version": "fhops.hydrology.crosswalk.v1",
        "crosswalk_id": "fixture-crosswalk",
        "created_utc": "2026-10-27T00:00:00+00:00",
        "review_status": review_status,
        "reviewed_by": reviewed_by,
        "method": "Explicit synthetic mapping",
        "source": "Synthetic fixture",
        "caveats": ["Synthetic crosswalk only."],
    }
    if crosswalk_sha256 is not None:
        payload["crosswalk_sha256"] = crosswalk_sha256
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_complete_crosswalk_maps_all_supports(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", _rows(scenario))
    metadata = _write_metadata(
        tmp_path / "crosswalk.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )

    mapping = map_femic_hydrology_to_scenario(
        scenario,
        BUNDLE,
        crosswalk,
        metadata_path=metadata,
        generated_utc="2026-10-27T00:00:00+00:00",
    )

    assert mapping.review_status == "reviewed"
    assert mapping.coverage["unmapped_blocks"] == []
    assert mapping.coverage["unmapped_landings"] == []
    assert mapping.coverage["unmapped_roads"] == []
    assert mapping.coverage["scenario_roads"] == 1
    assert any(row.support_unit == "road" and row.support_id == "R1" for row in mapping.rows)
    assert mapping.warnings == ()

    paths = write_hydrology_mapping(mapping, tmp_path / "mapping")
    assert paths["rows"].is_file()
    assert paths["manifest"].is_file()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "fhops.hydrology.mapping.v1"
    assert manifest["row_count"] == len(mapping.rows)
    assert manifest["coverage"]["unmapped_blocks"] == []


def test_partial_mapping_requires_opt_in(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", [_row(block_id="T6_23339490")])

    with pytest.raises(FemicHydrologyMappingError, match="does not cover"):
        map_femic_hydrology_to_scenario(scenario, BUNDLE, crosswalk)

    mapping = map_femic_hydrology_to_scenario(
        scenario,
        BUNDLE,
        crosswalk,
        allow_partial=True,
        generated_utc="2026-10-27T00:00:00+00:00",
    )
    assert mapping.coverage["unmapped_blocks"]
    assert mapping.coverage["unmapped_landings"] == ["L1"]
    assert mapping.coverage["unmapped_roads"] == ["R1"]
    assert any("Partial mapping" in warning for warning in mapping.warnings)


def test_unknown_support_and_femic_ids_fail(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    for bad, message in (
        (_row(block_id="B99"), "unknown block"),
        (_row(block_id="T6_23339490", unit_id="unit-99"), "unknown FEMIC unit"),
        (_row(block_id="T6_23339490", watershed_id="watershed-99"), "unknown FEMIC watershed"),
        (_row(block_id="T6_23339490", receptor_id="receptor-99"), "unknown FEMIC receptor"),
    ):
        crosswalk = _write_crosswalk(tmp_path / f"bad-{len(message)}.csv", [bad])
        with pytest.raises(FemicHydrologyMappingError, match=message):
            map_femic_hydrology_to_scenario(
                scenario,
                BUNDLE,
                crosswalk,
                allow_partial=True,
            )


def test_conflicting_unit_watershed_fails(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    crosswalk = _write_crosswalk(
        tmp_path / "conflict.csv",
        [_row(block_id="T6_23339490", watershed_id="watershed-2")],
    )

    with pytest.raises(FemicHydrologyMappingError, match="belongs to watershed"):
        map_femic_hydrology_to_scenario(
            scenario,
            BUNDLE,
            crosswalk,
            allow_partial=True,
        )


def test_crosswalk_rejects_duplicate_rows_and_bad_metadata(tmp_path: Path) -> None:
    row = _row(block_id="T6_23339490")
    crosswalk = _write_crosswalk(tmp_path / "duplicate.csv", [row, row])
    with pytest.raises(FemicHydrologyMappingError, match="Duplicate crosswalk support"):
        load_hydrology_crosswalk(crosswalk)

    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", [row])
    metadata = _write_metadata(tmp_path / "bad.meta.json", reviewed_by=None)
    with pytest.raises(FemicHydrologyMappingError, match="reviewed_by"):
        load_hydrology_crosswalk(crosswalk, metadata_path=metadata)

    metadata = _write_metadata(
        tmp_path / "bad-checksum.meta.json",
        crosswalk_sha256="0" * 64,
    )
    with pytest.raises(FemicHydrologyMappingError, match="checksum"):
        load_hydrology_crosswalk(crosswalk, metadata_path=metadata)


def test_mapping_requires_a_scenario_pin(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path, register=False)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", [_row(block_id="T6_23339490")])

    with pytest.raises(FemicHydrologyMappingError, match="not pinned"):
        map_femic_hydrology_to_scenario(scenario, BUNDLE, crosswalk, allow_partial=True)


def test_cli_map_writes_manifest(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", _rows(scenario))
    metadata = _write_metadata(
        tmp_path / "crosswalk.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )
    out = tmp_path / "mapping"

    result = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "map",
            str(scenario),
            str(BUNDLE),
            str(crosswalk),
            "--metadata",
            str(metadata),
            "--out",
            str(out),
        ],
        prog_name="fhops",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_status"] == "reviewed"
    assert (out / "hydrology_mapping.csv").is_file()
    assert (out / "hydrology_mapping.json").is_file()
