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


@pytest.mark.parametrize("samples", [1, 3, 5])
@pytest.mark.parametrize("seed", [0, 42, 1234])
def test_stochastic_defaults_match_deterministic(samples: int, seed: int):
    problem, assignments = _load_problem_and_assignments("minitoy")
    base = run_playback(problem, assignments)
    base_total = _total_production(base)

    config = SamplingConfig(samples=samples, base_seed=seed)
    config.downtime.enabled = False
    config.weather.enabled = False
    config.landing.enabled = False

    ensemble = run_stochastic_playback(problem, assignments, sampling_config=config)

    assert _total_production(ensemble.base_result) == pytest.approx(base_total, rel=1e-9)
    assert len(ensemble.samples) == samples
    for sample in ensemble.samples:
        assert _total_production(sample.result) == pytest.approx(base_total, rel=1e-9)


@pytest.mark.parametrize("downtime_prob", [0.1, 0.5])
@pytest.mark.parametrize("weather_prob", [0.0, 0.3])
def test_stochastic_production_bounds(downtime_prob: float, weather_prob: float):
    problem, assignments = _load_problem_and_assignments("minitoy")
    base = run_playback(problem, assignments)
    base_total = _total_production(base)

    config = SamplingConfig(samples=5, base_seed=777)
    config.downtime.enabled = downtime_prob > 0
    config.downtime.probability = downtime_prob
    config.weather.enabled = weather_prob > 0
    config.weather.day_probability = weather_prob
    config.weather.severity_levels = {"moderate": 0.25}
    config.landing.enabled = False

    ensemble = run_stochastic_playback(problem, assignments, sampling_config=config)

    for sample in ensemble.samples:
        total = _total_production(sample.result)
        assert 0.0 <= total <= base_total + 1e-6


def test_landing_shock_reduces_production():
    problem, assignments = _load_problem_and_assignments("med42")
    base = run_playback(problem, assignments)
    base_total = _total_production(base)

    config = SamplingConfig(samples=1, base_seed=2025)
    config.downtime.enabled = False
    config.weather.enabled = False
    config.landing.enabled = True
    config.landing.probability = 1.0
    config.landing.capacity_multiplier_range = (0.2, 0.2)
    config.landing.duration_days = 3

    ensemble = run_stochastic_playback(problem, assignments, sampling_config=config)
    sample = ensemble.samples[0].result
    total = _total_production(sample)
    assert total < base_total
