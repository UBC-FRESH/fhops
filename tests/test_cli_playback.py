from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.evaluation import PlaybackConfig, run_playback
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

runner = CliRunner()


def _solve_sa_assignments(scenario_path: str, tmp_path: Path) -> Path:
    result = runner.invoke(
        app,
        [
            "solve-heur",
            scenario_path,
            "--out",
            str(tmp_path / "assignments.csv"),
            "--iters",
            "50",
            "--seed",
            "123",
        ],
    )
    assert result.exit_code == 0, result.stdout
    return tmp_path / "assignments.csv"


def test_eval_playback_cli(tmp_path: Path):
    scenario_path = "tests/fixtures/regression/regression.yaml"
    assignments_path = _solve_sa_assignments(scenario_path, tmp_path)

    shift_out = tmp_path / "shift.csv"
    day_out = tmp_path / "day.csv"

    result = runner.invoke(
        app,
        [
            "eval-playback",
            scenario_path,
            "--assignments",
            str(assignments_path),
            "--shift-out",
            str(shift_out),
            "--day-out",
            str(day_out),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert shift_out.exists()
    assert day_out.exists()

    shift_df = pd.read_csv(shift_out)
    day_df = pd.read_csv(day_out)

    assert not shift_df.empty
    assert not day_df.empty

    sc = load_scenario(scenario_path)
    pb = Problem.from_scenario(sc)
    cli_playback = run_playback(pb, pd.read_csv(assignments_path), config=PlaybackConfig())

    assert shift_df["production_units"].sum() == pytest.approx(
        sum(summary.production_units for summary in cli_playback.shift_summaries)
    )
    assert day_df["production_units"].sum() == pytest.approx(
        sum(summary.production_units for summary in cli_playback.day_summaries)
    )
