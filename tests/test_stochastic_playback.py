from __future__ import annotations

import pandas as pd
import pytest

from fhops.evaluation import (
    PlaybackConfig,
    SamplingConfig,
    run_playback,
    run_stochastic_playback,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario


def _load_problem_and_assignments(name: str) -> tuple[Problem, pd.DataFrame]:
    scenario = load_scenario(f"examples/{name}/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = pd.read_csv(f"tests/fixtures/playback/{name}_assignments.csv")
    return problem, assignments


def _total_production(playback_result) -> float:
    return sum(summary.production_units for summary in playback_result.day_summaries)


def test_downtime_event_zeroes_production():
    problem, assignments = _load_problem_and_assignments("minitoy")
    config = SamplingConfig(samples=1, base_seed=123)
    config.downtime.enabled = True
    config.downtime.probability = 1.0
    config.weather.enabled = False

    result = run_stochastic_playback(problem, assignments, sampling_config=config)
    assert len(result.samples) == 1
    sample = result.samples[0].result
    assert pytest.approx(_total_production(sample), abs=1e-9) == 0.0


def test_weather_event_scales_production():
    problem, assignments = _load_problem_and_assignments("minitoy")
    base_playback = run_playback(problem, assignments)
    base_total = _total_production(base_playback)

    config = SamplingConfig(samples=1, base_seed=42)
    config.downtime.enabled = False
    config.weather.enabled = True
    config.weather.day_probability = 1.0
    config.weather.severity_levels = {"severe": 0.5}
    config.weather.impact_window_days = 1

    result = run_stochastic_playback(problem, assignments, sampling_config=config)
    sample_total = _total_production(result.samples[0].result)
    assert sample_total == pytest.approx(base_total * 0.5, rel=1e-6)
