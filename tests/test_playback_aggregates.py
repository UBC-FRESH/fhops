from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from fhops.evaluation import (
    PlaybackRecord,
    SamplingConfig,
    day_dataframe,
    day_dataframe_from_ensemble,
    compute_kpis,
    machine_utilisation_summary,
    run_playback,
    run_stochastic_playback,
    shift_dataframe,
    shift_dataframe_from_ensemble,
    summarise_days,
    summarise_shifts,
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


_playback_record_strategy = st.builds(
    PlaybackRecord,
    day=st.integers(min_value=1, max_value=7),
    shift_id=st.sampled_from(["S1", "S2"]),
    machine_id=st.sampled_from(["M1", "M2", "M3"]),
    block_id=st.sampled_from(["B1", "B2", "B3", "B4"]),
    hours_worked=st.floats(min_value=0.0, max_value=12.0, allow_nan=False, allow_infinity=False),
    production_units=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    mobilisation_cost=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    blackout_hit=st.booleans(),
)


@settings(max_examples=25, deadline=None)
@given(st.lists(_playback_record_strategy, min_size=1, max_size=20))
def test_blackout_conflicts_aggregate(records):
    availability_map = {
        (record.day, record.shift_id, record.machine_id): 10.0 for record in records
    }
    shift_summaries = list(
        summarise_shifts(
            records,
            availability_map,
            include_idle=False,
            sample_id=0,
        )
    )

    expected_shift_counts: Counter[tuple[int, str, str]] = Counter()
    for record in records:
        if record.blackout_hit:
            expected_shift_counts[(record.day, record.shift_id, record.machine_id)] += 1

    for summary in shift_summaries:
        key = (summary.day, summary.shift_id, summary.machine_id)
        assert summary.blackout_conflicts == expected_shift_counts.get(key, 0)
        assert summary.blackout_conflicts >= 0

    day_summaries = list(
        summarise_days(
            shift_summaries,
            availability_map,
            defaultdict(set),
            sample_id=0,
        )
    )

    expected_day_counts: Counter[int] = Counter()
    for (day, _shift_id, _machine_id), count in expected_shift_counts.items():
        expected_day_counts[day] += count

    for summary in day_summaries:
        assert summary.blackout_conflicts == expected_day_counts.get(summary.day, 0)
        assert summary.blackout_conflicts >= 0


@pytest.mark.parametrize("scenario_name", ["minitoy", "med42"])
def test_kpi_alignment_with_aggregates(scenario_name: str):
    scenario = load_scenario(f"examples/{scenario_name}/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = _load_assignments(scenario_name)

    playback = run_playback(problem, assignments)
    shift_df = shift_dataframe(playback)
    day_df = day_dataframe(playback)
    kpis = compute_kpis(problem, assignments)

    assert day_df["production_units"].sum() == pytest.approx(kpis["total_production"])
    assert day_df["completed_blocks"].sum() == pytest.approx(kpis["completed_blocks"])

    if "mobilisation_cost" in kpis:
        assert day_df["mobilisation_cost"].sum() == pytest.approx(kpis["mobilisation_cost"])

    if "sequencing_violation_count" in kpis:
        assert shift_df["sequencing_violations"].sum() == pytest.approx(
            kpis["sequencing_violation_count"]
        )
