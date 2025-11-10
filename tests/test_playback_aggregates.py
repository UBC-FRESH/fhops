from __future__ import annotations

import pandas as pd

from fhops.evaluation import (
    PlaybackConfig,
    day_dataframe,
    machine_utilisation_summary,
    run_playback,
    shift_dataframe,
)
from fhops.evaluation.playback.aggregates import shift_dataframe_from_ensemble
from fhops.evaluation.playback.stochastic import run_stochastic_playback
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario


def _load_assignments(name: str) -> pd.DataFrame:
    return pd.read_csv(f"tests/fixtures/playback/{name}_assignments.csv")


def test_shift_dataframe_matches_fixture():
    scenario = load_scenario("examples/minitoy/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = _load_assignments("minitoy")

    playback = run_playback(problem, assignments)
    df = shift_dataframe(playback).sort_values(["day", "machine_id"]).reset_index(drop=True)

    fixture = pd.read_csv("tests/fixtures/playback/minitoy_shift.csv").sort_values(
        ["day", "machine_id"]
    ).reset_index(drop=True)

    pd.testing.assert_frame_equal(df, fixture, check_dtype=False)


def test_day_dataframe_matches_fixture():
    scenario = load_scenario("examples/med42/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = _load_assignments("med42")

    playback = run_playback(problem, assignments)
    df = day_dataframe(playback).sort_values(["day"]).reset_index(drop=True)

    fixture = pd.read_csv("tests/fixtures/playback/med42_day.csv").sort_values(["day"]).reset_index(
        drop=True
    )
    pd.testing.assert_frame_equal(df, fixture, check_dtype=False)


def test_machine_utilisation_summary():
    scenario = load_scenario("examples/minitoy/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = _load_assignments("minitoy")

    playback = run_playback(problem, assignments)
    shift_df = shift_dataframe(playback)
    summary = machine_utilisation_summary(shift_df)

    assert {"sample_id", "machine_id", "utilisation_ratio"}.issubset(summary.columns)
    ratios = summary["utilisation_ratio"].dropna()
    assert (ratios <= 1.0001).all()


def test_shift_dataframe_from_ensemble_handles_samples():
    scenario = load_scenario("examples/minitoy/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = _load_assignments("minitoy")

    from fhops.evaluation import SamplingConfig

    cfg = SamplingConfig(samples=2, base_seed=7)
    cfg.downtime.enabled = False
    cfg.weather.enabled = False
    cfg.landing.enabled = False

    ensemble = run_stochastic_playback(problem, assignments, sampling_config=cfg)

    df = shift_dataframe_from_ensemble(ensemble)
    assert "sample_id" in df.columns
    assert df["sample_id"].nunique() == 2
