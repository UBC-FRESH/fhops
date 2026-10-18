"""Unit tests for the adaptive (Aarts and Van Laarhoven) SA cooling schedule."""

from __future__ import annotations

import math

import pytest

from fhops.optimization.heuristics.cooling import AdaptiveCooling, AdaptiveSchedule


def test_initial_temperature_uses_mean_uphill() -> None:
    rule = AdaptiveCooling(initial_acceptance=0.9)
    # Only positive increases count; c0 = mean / ln(1 / chi0).
    assert rule.initial_temperature([1.0, 3.0, -2.0, 0.0]) == pytest.approx(
        2.0 / math.log(1.0 / 0.9)
    )


def test_initial_temperature_zero_without_uphill() -> None:
    assert AdaptiveCooling().initial_temperature([0.0, -1.0]) == 0.0


def test_cool_follows_the_rule() -> None:
    rule = AdaptiveCooling(delta=0.1)
    temperature, spread = 10.0, 4.0
    expected = temperature / (1.0 + temperature * math.log1p(0.1) / (3.0 * spread))
    assert rule.cool(temperature, spread) == pytest.approx(expected)


def test_cool_leaves_temperature_when_spread_is_zero() -> None:
    assert AdaptiveCooling().cool(5.0, 0.0) == 5.0
    assert AdaptiveCooling().cool(5.0, -1.0) == 5.0


def test_rule_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError):
        AdaptiveCooling(initial_acceptance=1.0)
    with pytest.raises(ValueError):
        AdaptiveCooling(delta=0.0)


def test_schedule_warms_up_then_cools() -> None:
    schedule = AdaptiveSchedule(window=3, rule=AdaptiveCooling(initial_acceptance=0.9))
    # Warm-up: temperature is infinite and every move is accepted.
    assert schedule.temperature == math.inf
    schedule.observe(2.0, 100.0)
    schedule.observe(-1.0, 100.0)
    schedule.observe(4.0, 100.0)
    # Initial temperature from the mean uphill (3.0) / ln(1 / 0.9).
    assert schedule.temperature == pytest.approx(3.0 / math.log(1.0 / 0.9))
    before = schedule.temperature
    # Record scores; after a full window with zero spread the temperature is unchanged.
    schedule.observe(1.0, 100.0)
    schedule.observe(1.0, 100.0)
    assert schedule.temperature == pytest.approx(before)
    schedule.observe(1.0, 100.0)
    assert schedule.temperature == pytest.approx(before)


def test_schedule_reset_rearms_warm_up() -> None:
    schedule = AdaptiveSchedule(window=2)
    schedule.observe(2.0, 0.0)
    schedule.observe(2.0, 0.0)
    assert math.isfinite(schedule.temperature)
    schedule.reset()
    assert schedule.temperature == math.inf


def test_effective_window_caps_at_half_budget() -> None:
    assert AdaptiveSchedule.effective_window(40, None) == 20
    assert AdaptiveSchedule.effective_window(1000, None) == 64
    assert AdaptiveSchedule.effective_window(1000, 200) == 200
    assert AdaptiveSchedule.effective_window(1, None) == 1


def test_solve_sa_adaptive_flag_is_opt_in() -> None:
    from pathlib import Path

    from fhops.optimization.heuristics import solve_sa
    from fhops.scenario.contract import Problem
    from fhops.scenario.io import load_scenario

    root = Path(__file__).resolve().parents[2]
    pb = Problem.from_scenario(load_scenario(str(root / "examples" / "tiny7" / "scenario.yaml")))
    plain = solve_sa(pb, iters=20, seed=1)
    adaptive = solve_sa(pb, iters=20, seed=1, adaptive_cooling=True)
    assert plain["meta"]["adaptive_cooling"] is False
    assert "cooling_window" not in plain["meta"]
    assert adaptive["meta"]["adaptive_cooling"] is True
    assert adaptive["meta"]["cooling_window"] >= 1
