"""Tests for the scenario data-quality inspector."""

from __future__ import annotations

import shutil
from pathlib import Path

from fhops.scenario.data_quality import inspect_data_quality
from fhops.scenario.io import load_scenario

ROOT = Path(__file__).resolve().parents[2]
TINY7 = ROOT / "examples" / "tiny7" / "scenario.yaml"
LIDAR = ROOT / "examples" / "lidar_tfl6" / "scenario.yaml"


def test_non_standard_daily_hours_is_a_warning() -> None:
    scenario = load_scenario(TINY7)
    scenario.machines[0] = scenario.machines[0].model_copy(update={"daily_hours": 12.0})
    report = inspect_data_quality(scenario, TINY7)
    assert not report.errors
    assert any(issue.code == "machine_daily_hours" for issue in report.warnings)
    assert any(
        issue.entity_id == scenario.machines[0].id
        for issue in report.warnings
        if issue.code == "machine_daily_hours"
    )


def test_standard_dataset_has_no_machine_warnings() -> None:
    scenario = load_scenario(TINY7)
    report = inspect_data_quality(scenario, TINY7)
    assert not any(issue.code == "machine_daily_hours" for issue in report.issues)


def test_ground_support_is_consumed_when_valid() -> None:
    scenario = load_scenario(LIDAR)
    report = inspect_data_quality(scenario, LIDAR)
    assert not report.errors


def test_invalid_ground_support_checksum_is_an_error(tmp_path: Path) -> None:
    copied = tmp_path / "lidar"
    shutil.copytree(LIDAR.parent, copied)
    summary = copied / "ground_summary.csv"
    summary.write_text(summary.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    scenario = load_scenario(copied / "scenario.yaml")
    report = inspect_data_quality(scenario, copied / "scenario.yaml")
    assert any(issue.code == "ground_support_invalid" for issue in report.errors)
    assert report.to_dict()["error_count"] == 1
