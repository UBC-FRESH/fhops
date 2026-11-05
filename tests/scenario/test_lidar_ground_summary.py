"""Tests for the read-only FHOPS ground-summary support report."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.lidar_ground_summary import (
    GroundSummaryError,
    inspect_ground_summary,
    inspect_ground_support,
)

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "examples" / "tiny7" / "scenario.yaml"
FIXTURE = REPO / "examples" / "lidar_tfl6" / "scenario.yaml"
RUNNER = CliRunner()
COLUMNS = (
    "block_id",
    "point_count",
    "ground_count",
    "ground_fraction",
    "low_count",
    "low_fraction",
    "hag_mean",
    "hag_p50",
    "hag_p95",
    "hag_max",
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(block_id: str, ground_fraction: float = 0.5) -> dict[str, object]:
    return {
        "block_id": block_id,
        "point_count": 100,
        "ground_count": int(ground_fraction * 100),
        "ground_fraction": ground_fraction,
        "low_count": 10,
        "low_fraction": 0.1,
        "hag_mean": 8.0,
        "hag_p50": 6.0,
        "hag_p95": 20.0,
        "hag_max": 30.0,
    }


def test_inspect_ground_summary_matches_blocks(tmp_path: Path) -> None:
    """Matched, missing, and unknown block IDs are reported."""
    summary = _write_csv(tmp_path / "summary.csv", [_row("B01"), _row("B99")])
    report = inspect_ground_summary(SCENARIO, summary)
    assert [row.block_id for row in report.rows] == ["B01"]
    assert report.missing_block_ids == ("B02",)
    assert report.unknown_block_ids == ("B99",)
    assert any("no ground summary" in warning for warning in report.warnings)
    assert report.rows[0].hag_p95_m == 20.0


def test_inspect_ground_summary_rejects_missing_columns(tmp_path: Path) -> None:
    """A missing required column is an error."""
    summary = tmp_path / "summary.csv"
    summary.write_text("block_id,point_count\nB01,100\n", encoding="utf-8")
    with pytest.raises(GroundSummaryError, match="missing columns"):
        inspect_ground_summary(SCENARIO, summary)


def test_inspect_ground_summary_rejects_bad_fraction(tmp_path: Path) -> None:
    """A fraction outside [0, 1] is rejected."""
    summary = _write_csv(tmp_path / "summary.csv", [_row("B01", ground_fraction=1.5)])
    with pytest.raises(GroundSummaryError, match="fractions"):
        inspect_ground_summary(SCENARIO, summary)


def test_inspect_ground_summary_rejects_duplicate_blocks(tmp_path: Path) -> None:
    """Duplicate block rows are rejected."""
    summary = _write_csv(tmp_path / "summary.csv", [_row("B01"), _row("B01")])
    with pytest.raises(GroundSummaryError, match="duplicate"):
        inspect_ground_summary(SCENARIO, summary)


def test_ground_summary_cli(tmp_path: Path) -> None:
    """The CLI prints a read-only JSON report."""
    summary = _write_csv(tmp_path / "summary.csv", [_row("B01"), _row("B02")])
    result = RUNNER.invoke(
        app,
        [
            "scenario",
            "lidar",
            "ground-summary",
            str(SCENARIO),
            str(summary),
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 2
    assert payload["rows"][0]["block_id"] == "B01"
    assert SCENARIO.read_text(encoding="utf-8").count("ground_support") == 0


def test_inspect_ground_support_reads_the_scenario_reference() -> None:
    """The scenario-backed report resolves the relative CSV and verifies its checksum."""
    report = inspect_ground_support(FIXTURE)
    assert len(report.rows) == 7
    assert report.missing_block_ids == ()
    assert report.unknown_block_ids == ()
    assert report.warnings == ()
    assert report.reference is not None
    assert report.reference.summary_path == "ground_summary.csv"
    assert report.reference.id_field == "polygon_id"
    assert report.rows[0].block_id == "T6_16624698"


def test_inspect_ground_support_requires_the_scenario_section() -> None:
    """A scenario without ground_support cannot use the scenario-backed report."""
    with pytest.raises(GroundSummaryError, match="no ground_support"):
        inspect_ground_support(SCENARIO)


def test_inspect_ground_support_rejects_a_checksum_mismatch(tmp_path: Path) -> None:
    """Changing the summary bytes is rejected before block matching."""
    target = tmp_path / "lidar_tfl6"
    shutil.copytree(FIXTURE.parent, target)
    summary = target / "ground_summary.csv"
    summary.write_text(summary.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(GroundSummaryError, match="sha256 mismatch"):
        inspect_ground_support(target / "scenario.yaml")


def test_inspect_ground_support_rejects_a_missing_file(tmp_path: Path) -> None:
    """A missing referenced CSV fails clearly."""
    target = tmp_path / "lidar_tfl6"
    shutil.copytree(FIXTURE.parent, target)
    (target / "ground_summary.csv").unlink()
    with pytest.raises(GroundSummaryError, match="does not exist"):
        inspect_ground_support(target / "scenario.yaml")


def test_ground_support_cli() -> None:
    """The scenario-backed CLI prints the matched report and reference."""
    result = RUNNER.invoke(
        app,
        ["scenario", "lidar", "ground-support", str(FIXTURE), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 7
    assert payload["missing_block_ids"] == []
    assert payload["ground_support"]["summary_path"] == "ground_summary.csv"
    assert payload["ground_support"]["id_field"] == "polygon_id"
