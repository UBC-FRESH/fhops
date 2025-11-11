from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import given, settings, strategies as st

from fhops.evaluation import (
    SamplingConfig,
    day_dataframe,
    day_dataframe_from_ensemble,
    machine_utilisation_summary,
    run_playback,
    run_stochastic_playback,
    shift_dataframe,
    shift_dataframe_from_ensemble,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario


def _load_assignments(name: str) -> pd.DataFrame:
    return pd.read_csv(f"tests/fixtures/playback/{name}_assignments.csv")


def test_shift_dataframe_matches_fixture():
    scenario = load_scenario("examples/minitoy/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = _load_assignments("minitoy")

    playback = run_playback(problem, assignments)
    df = shift_dataframe(playback)
    df = df.reindex(sorted(df.columns), axis=1).sort_values(["day", "machine_id"]).reset_index(drop=True)

    fixture = pd.read_csv("tests/fixtures/playback/minitoy_shift.csv").sort_values(
        ["day", "machine_id"]
    ).reset_index(drop=True)
    fixture = fixture.reindex(sorted(fixture.columns), axis=1)

    pd.testing.assert_frame_equal(df, fixture, check_dtype=False)


def test_day_dataframe_matches_fixture():
    scenario = load_scenario("examples/med42/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = _load_assignments("med42")

    playback = run_playback(problem, assignments)
    df = day_dataframe(playback)
    df = df.reindex(sorted(df.columns), axis=1).sort_values(["day"]).reset_index(drop=True)

    fixture = pd.read_csv("tests/fixtures/playback/med42_day.csv").sort_values(["day"]).reset_index(
        drop=True
    )
    fixture = fixture.reindex(sorted(fixture.columns), axis=1)
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

    cfg = SamplingConfig(samples=2, base_seed=7)
    cfg.downtime.enabled = False
    cfg.weather.enabled = False
    cfg.landing.enabled = False

    ensemble = run_stochastic_playback(problem, assignments, sampling_config=cfg)

    df = shift_dataframe_from_ensemble(ensemble)
    assert "sample_id" in df.columns
    assert df["sample_id"].nunique() == 2


def _build_sampling_config(
    samples: int, enable_downtime: bool, enable_weather: bool, enable_landing: bool
) -> SamplingConfig:
    cfg = SamplingConfig(samples=samples, base_seed=11)
    cfg.downtime.enabled = enable_downtime
    cfg.downtime.probability = 0.7 if enable_downtime else 0.0
    cfg.downtime.max_concurrent = 2 if enable_downtime else None

    cfg.weather.enabled = enable_weather
    cfg.weather.day_probability = 0.5 if enable_weather else 0.0
    cfg.weather.severity_levels = {"default": 0.4} if enable_weather else {}
    cfg.weather.impact_window_days = 2

    cfg.landing.enabled = enable_landing
    cfg.landing.probability = 0.6 if enable_landing else 0.0
    cfg.landing.capacity_multiplier_range = (0.3, 0.8)
    cfg.landing.duration_days = 2
    return cfg


@settings(max_examples=5, deadline=None)
@given(
    samples=st.integers(min_value=1, max_value=3),
    enable_downtime=st.booleans(),
    enable_weather=st.booleans(),
    enable_landing=st.booleans(),
)
def test_shift_totals_match_day_totals(samples, enable_downtime, enable_weather, enable_landing):
    scenario = load_scenario("examples/med42/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = _load_assignments("med42")

    cfg = _build_sampling_config(samples, enable_downtime, enable_weather, enable_landing)
    result = run_stochastic_playback(problem, assignments, sampling_config=cfg)

    if result.samples:
        shift_df = shift_dataframe_from_ensemble(result)
        day_df = day_dataframe_from_ensemble(result)
    else:
        shift_df = shift_dataframe(result.base_result)
        day_df = day_dataframe(result.base_result)

    if day_df.empty:
        # No day summaries when schedule fully suppressed; ensure matching emptiness.
        assert shift_df.empty
        return

    # Prepare comparison data.
    day_totals = day_df.fillna(0.0)
    shift_totals = (
        shift_df.fillna(0.0)
        .groupby(["sample_id", "day"], dropna=False)
        .agg(
            production_units=("production_units", "sum"),
            total_hours=("total_hours", "sum"),
            mobilisation_cost=("mobilisation_cost", "sum"),
            blackout_conflicts=("blackout_conflicts", "sum"),
            sequencing_violations=("sequencing_violations", "sum"),
            available_hours=("available_hours", "sum"),
        )
        .reset_index()
    )

    merged = day_totals.merge(
        shift_totals,
        on=["sample_id", "day"],
        how="left",
        suffixes=("_day", "_shift"),
    ).fillna(0.0)

    columns = [
        "production_units",
        "total_hours",
        "mobilisation_cost",
        "blackout_conflicts",
        "sequencing_violations",
    ]

    for column in columns:
        day_vals = merged[f"{column}_day"].to_numpy(dtype=float)
        shift_vals = merged[f"{column}_shift"].to_numpy(dtype=float)
        assert np.allclose(day_vals, shift_vals, atol=1e-6), f"Mismatched totals for {column}"

    available_day = merged["available_hours_day"].to_numpy(dtype=float)
    available_shift = merged["available_hours_shift"].to_numpy(dtype=float)
    assert np.all(available_day + 1e-6 >= available_shift)
