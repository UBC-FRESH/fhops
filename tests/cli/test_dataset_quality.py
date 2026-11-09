"""CLI tests for the dataset quality inspector."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from fhops.cli.dataset import dataset_app
from fhops.cli.main import app
from tests.cli import CliRunner, cli_text

ROOT = Path(__file__).resolve().parents[2]
TINY7 = ROOT / "examples" / "tiny7"


def _scenario_with_daily_hours(tmp_path: Path, hours: float) -> Path:
    copied = tmp_path / "tiny7"
    shutil.copytree(TINY7, copied)
    machines_path = copied / "data" / "machines.csv"
    frame = pd.read_csv(machines_path)
    frame.loc[0, "daily_hours"] = hours
    frame.to_csv(machines_path, index=False)
    return copied / "scenario.yaml"


def test_inspect_quality_reports_daily_hours_warning(tmp_path: Path) -> None:
    scenario = _scenario_with_daily_hours(tmp_path, 12.0)
    json_path = tmp_path / "quality.json"
    result = CliRunner().invoke(
        dataset_app,
        [
            "inspect-quality",
            "--dataset",
            str(scenario),
            "--no-interactive",
            "--json-out",
            str(json_path),
        ],
    )
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "machine_daily_hours" in text
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["warning_count"] >= 1
    assert any(issue["code"] == "machine_daily_hours" for issue in payload["issues"])


def test_inspect_quality_fail_on_warning(tmp_path: Path) -> None:
    scenario = _scenario_with_daily_hours(tmp_path, 12.0)
    result = CliRunner().invoke(
        dataset_app,
        [
            "inspect-quality",
            "--dataset",
            str(scenario),
            "--no-interactive",
            "--fail-on-warning",
        ],
    )
    assert result.exit_code == 1


def test_validate_surfaces_data_quality_warning(tmp_path: Path) -> None:
    scenario = _scenario_with_daily_hours(tmp_path, 12.0)
    result = CliRunner().invoke(app, ["validate", str(scenario)])
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "Warning: machine" in text
    assert "differs from the 24 h/day baseline" in text
