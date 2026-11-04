from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fhops.cli.main import app

from .cli import CliRunner

runner = CliRunner()
TINY7 = Path("examples/tiny7/scenario.yaml")


def test_report_salvage_shelf_life_writes_outputs(tmp_path: Path):
    storage = tmp_path / "storage.csv"
    pd.DataFrame(
        {
            "block_id": ["B01", "B02"],
            "years_since_disturbance": [1.0, 4.0],
        }
    ).to_csv(storage, index=False)
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "report",
            "salvage-shelf-life",
            str(TINY7),
            str(storage),
            "--value-per-m3",
            "10",
            "--out-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "pnw_fire_killed_mixed_conifer" in result.output
    assert "Read-only report" in result.output
    assert (out_dir / "salvage_shelf_life.csv").exists()
    assert (out_dir / "salvage_shelf_life.md").exists()


def test_report_salvage_shelf_life_rejects_unknown_block(tmp_path: Path):
    storage = tmp_path / "storage.csv"
    pd.DataFrame({"block_id": ["NOPE"], "years_since_disturbance": [1.0]}).to_csv(
        storage, index=False
    )

    result = runner.invoke(
        app,
        ["report", "salvage-shelf-life", str(TINY7), str(storage)],
    )

    assert result.exit_code == 1
    assert "not present in the scenario" in result.output


def test_report_salvage_shelf_life_rejects_bad_curve(tmp_path: Path):
    storage = tmp_path / "storage.csv"
    pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [1.0]}).to_csv(
        storage, index=False
    )

    result = runner.invoke(
        app,
        ["report", "salvage-shelf-life", str(TINY7), str(storage), "--curve", "missing"],
    )

    assert result.exit_code == 1
    assert "unknown salvage decay curve" in result.output


@pytest.mark.parametrize("age", ["-1", "not-a-number"])
def test_report_salvage_shelf_life_rejects_bad_age(tmp_path: Path, age: str):
    storage = tmp_path / "storage.csv"
    pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [age]}).to_csv(
        storage, index=False
    )

    result = runner.invoke(
        app,
        ["report", "salvage-shelf-life", str(TINY7), str(storage)],
    )

    assert result.exit_code == 1
    assert "years_since_disturbance" in result.output
