from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from fhops.evaluation import (
    SamplingConfig,
    run_playback,
    run_stochastic_playback,
)
from fhops.evaluation.playback import (
    DowntimeEvent,
    DowntimeEventConfig,
    LandingShockConfig,
    LandingShockEvent,
    SamplingContext,
    WeatherEventConfig,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.scenario.synthetic import SyntheticDatasetConfig, sampling_config_for
from fhops.scheduling.timeline import ShiftDefinition, TimelineConfig


def _load_problem_and_assignments(name: str) -> tuple[Problem, pd.DataFrame]:
    scenario = load_scenario(f"examples/{name}/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    assignments = pd.read_csv(f"tests/fixtures/playback/{name}_assignments.csv")
    return problem, assignments


def _total_production(playback_result) -> float:
    return sum(summary.production_units for summary in playback_result.day_summaries)


def test_downtime_full_shift_loss_zeroes_production():
    problem, assignments = _load_problem_and_assignments("tiny7")
    config = SamplingConfig(samples=1, base_seed=123)
    config.downtime.enabled = True
    config.downtime.probability = 1.0
    # Durations are clipped to the 24 h shift, so every hit is a full-shift loss.
    config.downtime.mean_duration_hours = 100.0
    config.downtime.std_duration_hours = 0.0
    config.weather.enabled = False
    config.landing.enabled = False

    result = run_stochastic_playback(problem, assignments, sampling_config=config)
    assert len(result.samples) == 1
    sample = result.samples[0].result
    assert pytest.approx(_total_production(sample), abs=1e-9) == 0.0
    downtime_records = [record for record in sample.records if record.downtime]
    assert len(downtime_records) == len(assignments)
    assert all(record.downtime_hours == pytest.approx(24.0) for record in downtime_records)
    assert all(record.hours_worked == 0.0 for record in downtime_records)
    assert sum(s.downtime_hours for s in sample.shift_summaries) == pytest.approx(
        24.0 * len(assignments)
    )


def _context(problem: Problem, seed: int, rng=None) -> SamplingContext:
    return SamplingContext(
        problem=problem,
        sample_id=0,
        rng=rng if rng is not None else np.random.default_rng(seed),
        config=SamplingConfig(),
    )


def test_downtime_event_full_loss_sets_assigned_zero():
    problem, assignments = _load_problem_and_assignments("tiny7")
    event = DowntimeEvent(
        DowntimeEventConfig(probability=1.0, mean_duration_hours=30.0, std_duration_hours=0.0)
    )
    out = event.apply(_context(problem, 1), assignments, {})
    assert (out["assigned"] == 0).all()
    assert (out["production"] == 0.0).all()
    assert (out["_downtime"] == 1).all()
    assert out["_downtime_hours"].tolist() == pytest.approx([24.0] * len(out))


def test_downtime_event_partial_loss_proportional_to_sampled_hours():
    problem, assignments = _load_problem_and_assignments("tiny7")
    event = DowntimeEvent(
        DowntimeEventConfig(probability=1.0, mean_duration_hours=8.0, std_duration_hours=3.0)
    )
    out = event.apply(_context(problem, 7), assignments, {})
    hours = out["_downtime_hours"]
    assert (hours > 0).all() and (hours < 24.0).all()
    assert hours.nunique() > 1  # durations are sampled, not constant
    expected = assignments["production"] * (1.0 - hours / 24.0)
    np.testing.assert_allclose(out["production"].to_numpy(), expected.to_numpy())
    assert (out["assigned"] == 1).all()

    # Same seed reproduces the same draws.
    again = event.apply(_context(problem, 7), assignments, {})
    pd.testing.assert_frame_equal(out, again)


def test_downtime_partial_loss_flows_into_playback_hours():
    problem, assignments = _load_problem_and_assignments("tiny7")
    config = SamplingConfig(samples=2, base_seed=5)
    config.downtime.probability = 0.5
    config.downtime.mean_duration_hours = 6.0
    config.downtime.std_duration_hours = 2.0
    config.weather.enabled = False
    config.landing.enabled = False

    ensemble = run_stochastic_playback(problem, assignments, sampling_config=config)
    for sample in ensemble.samples:
        for record in sample.result.records:
            if record.downtime:
                assert record.downtime_hours is not None
                assert 0.0 < record.downtime_hours <= 24.0
                assert record.hours_worked == pytest.approx(24.0 - record.downtime_hours)
            else:
                assert record.hours_worked == pytest.approx(24.0)
        expected_hours = sum(r.downtime_hours or 0.0 for r in sample.result.records)
        assert sum(s.downtime_hours for s in sample.result.shift_summaries) == pytest.approx(
            expected_hours
        )
        assert expected_hours > 0


def test_downtime_uses_timeline_shift_hours():
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    scenario = scenario.model_copy(
        update={
            "timeline": TimelineConfig(
                shifts=[ShiftDefinition(name="S1", hours=10.0, shifts_per_day=1)]
            )
        }
    )
    problem = Problem.from_scenario(scenario)
    assignments = pd.read_csv("tests/fixtures/playback/tiny7_assignments.csv")
    event = DowntimeEvent(
        DowntimeEventConfig(probability=1.0, mean_duration_hours=4.0, std_duration_hours=0.0)
    )
    out = event.apply(_context(problem, 3), assignments, {})
    np.testing.assert_allclose(
        out["production"].to_numpy(), (assignments["production"] * 0.6).to_numpy()
    )


def test_downtime_max_concurrent_hits_fixed_count_per_day():
    problem, assignments = _load_problem_and_assignments("tiny7")
    event = DowntimeEvent(
        DowntimeEventConfig(
            probability=0.1, mean_duration_hours=4.0, std_duration_hours=1.0, max_concurrent=1
        )
    )
    out = event.apply(_context(problem, 11), assignments, {})
    per_day = out.groupby("day")["_downtime"].sum()
    assert (per_day == 1).all()


class _ScriptedRng:
    """Minimal RNG stub returning scripted draws for landing-shock tests."""

    def __init__(self, randoms: list[float], uniforms: list[float]):
        self._randoms = list(randoms)
        self._uniforms = list(uniforms)

    def random(self) -> float:
        return self._randoms.pop(0)

    def uniform(self, low: float, high: float) -> float:
        value = self._uniforms.pop(0)
        assert low <= value <= high
        return value


def _landing_problem() -> Problem:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    return Problem.from_scenario(scenario)


def _full_landing_assignments(problem: Problem) -> pd.DataFrame:
    """Two machines on both blocks (landings L1/L2) every day of the horizon."""
    rows = [
        {
            "machine_id": machine,
            "block_id": block,
            "day": day,
            "shift_id": "S1",
            "assigned": 1,
            "production": 100.0,
        }
        for day in problem.days
        for block, machine in (("B01", "H1"), ("B01", "H2"), ("B02", "H3"), ("B02", "H4"))
    ]
    return pd.DataFrame(rows)


def test_landing_shock_hits_all_assignments_for_duration_days():
    problem = _landing_problem()
    assignments = _full_landing_assignments(problem)
    # Landing L1: shocks start on day 2 (0.5) and day 3 (0.4); L2: none.
    # tiny7 has 7 days -> 7 draws per landing.
    l1 = [0.9, 0.05, 0.05, 0.9, 0.9, 0.9, 0.9]
    l2 = [0.9] * 7
    rng = _ScriptedRng(l1 + l2, [0.5, 0.4])
    config = LandingShockConfig(
        probability=0.1, capacity_multiplier_range=(0.3, 0.6), duration_days=2
    )
    out = LandingShockEvent(config).apply(_context(problem, 0, rng=rng), assignments, {})

    expected_l1 = {1: 1.0, 2: 0.5, 3: 0.4, 4: 0.4, 5: 1.0, 6: 1.0, 7: 1.0}
    for _, row in out.iterrows():
        if row["block_id"] == "B01":
            assert row["production"] == pytest.approx(100.0 * expected_l1[int(row["day"])])
        else:
            assert row["production"] == pytest.approx(100.0)
    # Both machines on the landing are affected on every shocked day, not just the first rows.
    shocked = out[(out["block_id"] == "B01") & (out["production"] < 100.0)]
    assert sorted(shocked["day"].unique().tolist()) == [2, 3, 4]
    assert shocked.groupby("day")["machine_id"].nunique().eq(2).all()


def test_landing_shock_overlap_takes_minimum_multiplier():
    problem = _landing_problem()
    rng = _ScriptedRng([0.0, 0.0] + [0.9] * 5 + [0.9] * 7, [0.3, 0.6])
    config = LandingShockConfig(
        probability=0.2, capacity_multiplier_range=(0.3, 0.6), duration_days=3
    )
    multipliers = LandingShockEvent(config).sample_multipliers(_context(problem, 0, rng=rng))
    # Shock A: days 1-3 at 0.3; shock B: days 2-4 at 0.6 -> min on overlap.
    assert multipliers == {
        ("L1", 1): 0.3,
        ("L1", 2): 0.3,
        ("L1", 3): 0.3,
        ("L1", 4): 0.6,
    }


def test_landing_shock_seeded_apply_matches_sampled_map():
    problem, assignments = _load_problem_and_assignments("med42")
    assignments = assignments.assign(production=100.0)
    config = LandingShockConfig(
        probability=0.15, capacity_multiplier_range=(0.4, 0.8), duration_days=3
    )
    event = LandingShockEvent(config)
    multipliers = event.sample_multipliers(_context(problem, 99))
    assert multipliers
    out = event.apply(_context(problem, 99), assignments, {})
    landing_of = {block.id: block.landing_id for block in problem.scenario.blocks}
    for idx, row in out.iterrows():
        factor = multipliers.get((landing_of[row["block_id"]], int(row["day"])), 1.0)
        assert row["production"] == pytest.approx(assignments.loc[idx, "production"] * factor)


def test_correlated_days_warns_only_when_set_explicitly():
    with pytest.warns(DeprecationWarning, match="correlated_days"):
        WeatherEventConfig(correlated_days=True)
    with pytest.warns(DeprecationWarning, match="correlated_days"):
        SamplingConfig.model_validate({"weather": {"correlated_days": False}})

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        WeatherEventConfig()
        WeatherEventConfig(impact_window_days=3)
        SamplingConfig()
        SamplingConfig(samples=2).weather.correlated_days  # noqa: B018 - attribute access only
        sampling_config_for(
            SyntheticDatasetConfig(
                name="medium", tier="medium", num_blocks=4, num_days=5, num_machines=3
            )
        )


def test_weather_event_scales_production():
    problem, assignments = _load_problem_and_assignments("tiny7")
    base_playback = run_playback(problem, assignments)
    base_total = _total_production(base_playback)

    config = SamplingConfig(samples=1, base_seed=42)
    config.downtime.enabled = False
    config.weather.enabled = True
    config.weather.day_probability = 1.0
    config.weather.severity_levels = {"severe": 0.5}
    config.weather.impact_window_days = 1
    # Landing shocks are enabled by default (p=0.1 per landing-day); isolate weather.
    config.landing.enabled = False

    result = run_stochastic_playback(problem, assignments, sampling_config=config)
    sample_total = _total_production(result.samples[0].result)
    assert sample_total == pytest.approx(base_total * 0.5, rel=1e-6)


@pytest.mark.parametrize("samples", [1, 3, 5])
@pytest.mark.parametrize("seed", [0, 42, 1234])
def test_stochastic_defaults_match_deterministic(samples: int, seed: int):
    problem, assignments = _load_problem_and_assignments("tiny7")
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
    problem, assignments = _load_problem_and_assignments("tiny7")
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
