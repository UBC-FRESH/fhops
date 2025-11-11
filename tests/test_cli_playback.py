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


def _total_production(playback_result) -> float:
    return sum(summary.production_units for summary in playback_result.day_summaries)


def test_eval_playback_cli(tmp_path: Path):
    scenario_path = "tests/fixtures/regression/regression.yaml"
    assignments_path = _solve_sa_assignments(scenario_path, tmp_path)

    shift_out = tmp_path / "shift.csv"
    day_out = tmp_path / "day.csv"
    summary_md = tmp_path / "summary.md"

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
            "--summary-md",
            str(summary_md),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert shift_out.exists()
    assert day_out.exists()
    assert summary_md.exists()

    shift_df = pd.read_csv(shift_out)
    day_df = pd.read_csv(day_out)

    assert not shift_df.empty
    assert not day_df.empty
    summary_text = summary_md.read_text(encoding="utf-8")
    assert "Playback Summary" in summary_text
    assert "Total production units" in summary_text

    sc = load_scenario(scenario_path)
    pb = Problem.from_scenario(sc)
    cli_playback = run_playback(pb, pd.read_csv(assignments_path), config=PlaybackConfig())

    assert shift_df["production_units"].sum() == pytest.approx(
        sum(summary.production_units for summary in cli_playback.shift_summaries)
    )
    assert day_df["production_units"].sum() == pytest.approx(
        sum(summary.production_units for summary in cli_playback.day_summaries)
    )


def test_eval_playback_cli_stochastic(tmp_path: Path):
    scenario_path = "tests/fixtures/regression/regression.yaml"
    assignments_path = _solve_sa_assignments(scenario_path, tmp_path)

    shift_out = tmp_path / "shift.csv"
    day_out = tmp_path / "day.csv"

    samples = 3

    result = runner.invoke(
        app,
        [
            "eval-playback",
            scenario_path,
            "--assignments",
            str(assignments_path),
            "--samples",
            str(samples),
            "--downtime-prob",
            "1.0",
            "--shift-out",
            str(shift_out),
            "--day-out",
            str(day_out),
        ],
    )
    assert result.exit_code == 0, result.stdout

    shift_df = pd.read_csv(shift_out)
    day_df = pd.read_csv(day_out)

    # All production zero due to downtime probability 1.0
    assert pytest.approx(shift_df["production_units"].sum(), abs=1e-9) == 0.0
    assert pytest.approx(day_df["production_units"].sum(), abs=1e-9) == 0.0

    assert shift_df.empty

    base = run_playback(
        Problem.from_scenario(load_scenario(scenario_path)),
        pd.read_csv(assignments_path),
    )
    base_day_len = len(base.day_summaries)
    assert len(day_df) == base_day_len * samples


def test_eval_playback_cli_landing(tmp_path: Path):
    scenario_path = "tests/fixtures/regression/regression.yaml"
    assignments_path = _solve_sa_assignments(scenario_path, tmp_path)

    shift_out = tmp_path / "shift_landing.csv"
    day_out = tmp_path / "day_landing.csv"

    result = runner.invoke(
        app,
        [
            "eval-playback",
            scenario_path,
            "--assignments",
            str(assignments_path),
            "--samples",
            "2",
            "--landing-prob",
            "1.0",
            "--landing-mult-min",
            "0.2",
            "--landing-mult-max",
            "0.2",
            "--landing-duration",
            "2",
            "--shift-out",
            str(shift_out),
            "--day-out",
            str(day_out),
        ],
    )
    assert result.exit_code == 0, result.stdout

    day_df = pd.read_csv(day_out)
    base_total = _total_production(
        run_playback(
            Problem.from_scenario(load_scenario(scenario_path)),
            pd.read_csv(assignments_path),
        )
    )

    assert day_df["production_units"].sum() < base_total * 2


def test_evaluate_cli_basic_kpi_mode(tmp_path: Path):
    scenario_path = "tests/fixtures/regression/regression.yaml"
    assignments_path = _solve_sa_assignments(scenario_path, tmp_path)

    result = runner.invoke(
        app,
        [
            "evaluate",
            scenario_path,
            "--assignments",
            str(assignments_path),
            "--kpi-mode",
            "basic",
        ],
    )
    assert result.exit_code == 0, result.stdout
    stdout = result.stdout
    assert "KPI Summary" in stdout
    assert "Production" in stdout
    assert "Downtime" not in stdout
    assert "Weather" not in stdout


@pytest.mark.parametrize("scenario_name", ["minitoy", "med42"])
def test_playback_fixture_matches_cli(tmp_path: Path, scenario_name: str):
    scenario_path = Path(f"examples/{scenario_name}/scenario.yaml")
    assignments_fixture = Path(f"tests/fixtures/playback/{scenario_name}_assignments.csv")
    shift_fixture = Path(f"tests/fixtures/playback/{scenario_name}_shift.csv")
    day_fixture = Path(f"tests/fixtures/playback/{scenario_name}_day.csv")
    shift_parquet_fixture = Path(f"tests/fixtures/playback/{scenario_name}_shift.parquet")
    day_parquet_fixture = Path(f"tests/fixtures/playback/{scenario_name}_day.parquet")

    assert assignments_fixture.exists()
    assert shift_fixture.exists()
    assert day_fixture.exists()
    assert shift_parquet_fixture.exists()
    assert day_parquet_fixture.exists()

    shift_out = tmp_path / f"{scenario_name}_shift.csv"
    day_out = tmp_path / f"{scenario_name}_day.csv"
    shift_parquet_out = tmp_path / f"{scenario_name}_shift.parquet"
    day_parquet_out = tmp_path / f"{scenario_name}_day.parquet"

    result = runner.invoke(
        app,
        [
            "eval-playback",
            str(scenario_path),
            "--assignments",
            str(assignments_fixture),
            "--shift-out",
            str(shift_out),
            "--day-out",
            str(day_out),
            "--shift-parquet",
            str(shift_parquet_out),
            "--day-parquet",
            str(day_parquet_out),
        ],
    )
    assert result.exit_code == 0, result.stdout

    shift_df_cli = pd.read_csv(shift_out)
    day_df_cli = pd.read_csv(day_out)
    shift_df_fixture = pd.read_csv(shift_fixture)
    day_df_fixture = pd.read_csv(day_fixture)

    pd.testing.assert_frame_equal(
        shift_df_cli.sort_values(list(shift_df_cli.columns)).reset_index(drop=True),
        shift_df_fixture.sort_values(list(shift_df_fixture.columns)).reset_index(drop=True),
        check_dtype=False,
    )
    pd.testing.assert_frame_equal(
        day_df_cli.sort_values(list(day_df_cli.columns)).reset_index(drop=True),
        day_df_fixture.sort_values(list(day_df_fixture.columns)).reset_index(drop=True),
        check_dtype=False,
    )

    pytest.importorskip("pyarrow", reason="Parquet fixtures require pyarrow or fastparquet")
    shift_parquet_cli = pd.read_parquet(shift_parquet_out)
    day_parquet_cli = pd.read_parquet(day_parquet_out)
    shift_parquet_fixture_df = pd.read_parquet(shift_parquet_fixture)
    day_parquet_fixture_df = pd.read_parquet(day_parquet_fixture)

    pd.testing.assert_frame_equal(
        shift_parquet_cli.sort_values(list(shift_parquet_cli.columns)).reset_index(drop=True),
        shift_parquet_fixture_df.sort_values(list(shift_parquet_fixture_df.columns)).reset_index(drop=True),
        check_dtype=False,
    )
    pd.testing.assert_frame_equal(
        day_parquet_cli.sort_values(list(day_parquet_cli.columns)).reset_index(drop=True),
        day_parquet_fixture_df.sort_values(list(day_parquet_fixture_df.columns)).reset_index(drop=True),
        check_dtype=False,
    )
