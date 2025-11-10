from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from fhops.cli.main import app

runner = CliRunner()


@pytest.mark.parametrize(
    "scenario_name",
    [
        "examples/minitoy/scenario.yaml",
        "examples/med42/scenario.yaml",
        "tests/fixtures/regression/regression.yaml",
    ],
)
def test_eval_playback_exports_all_formats(tmp_path: Path, scenario_name: str):
    assignments = _resolve_assignments_fixture(scenario_name, tmp_path)

    shift_csv = tmp_path / "shift.csv"
    day_csv = tmp_path / "day.csv"
    shift_parquet = tmp_path / "shift.parquet"
    day_parquet = tmp_path / "day.parquet"
    summary_md = tmp_path / "summary.md"

    result = runner.invoke(
        app,
        [
            "eval-playback",
            scenario_name,
            "--assignments",
            str(assignments),
            "--samples",
            "2",
            "--shift-out",
            str(shift_csv),
            "--day-out",
            str(day_csv),
            "--shift-parquet",
            str(shift_parquet),
            "--day-parquet",
            str(day_parquet),
            "--summary-md",
            str(summary_md),
        ],
    )
    assert result.exit_code == 0, result.stdout

    # CSV checks
    shift_df = pd.read_csv(shift_csv)
    day_df = pd.read_csv(day_csv)
    assert not shift_df.empty
    assert not day_df.empty
    assert {"sample_id", "utilisation_ratio"}.issubset(shift_df.columns)
    assert {"sample_id", "utilisation_ratio"}.issubset(day_df.columns)

    # Parquet checks (skip if engine missing)
    pytest.importorskip("pyarrow", reason="Parquet exports require pyarrow or fastparquet")
    shift_parquet_df = pd.read_parquet(shift_parquet)
    day_parquet_df = pd.read_parquet(day_parquet)
    pd.testing.assert_frame_equal(
        shift_df.sort_index(axis=1), shift_parquet_df.sort_index(axis=1), check_dtype=False
    )
    pd.testing.assert_frame_equal(
        day_df.sort_index(axis=1), day_parquet_df.sort_index(axis=1), check_dtype=False
    )

    # Markdown summary checks
    summary = summary_md.read_text(encoding="utf-8")
    assert "Playback Summary" in summary
    assert "Samples:" in summary
    assert "Total production units" in summary


def _resolve_assignments_fixture(scenario_path: str, tmp_path: Path) -> Path:
    if scenario_path.startswith("examples/"):
        name = scenario_path.split("/")[1]
        fixture = Path("tests/fixtures/playback") / f"{name}_assignments.csv"
        if fixture.exists():
            return fixture

    # fallback: generate assignments via CLI
    assignments = tmp_path / "assignments.csv"
    result = runner.invoke(
        app,
        [
            "solve-mip",
            scenario_path,
            "--out",
            str(assignments),
            "--time-limit",
            "20",
        ],
    )
    if result.exit_code != 0:
        raise AssertionError(result.stdout)
    return assignments
