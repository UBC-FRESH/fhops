"""Tests for the selection-cut careful-logging trade-off."""

from __future__ import annotations

import pytest

from fhops.game.careful_logging import DEFAULT_CAREFUL_LOGGING_CURVE


def test_default_curve_has_interior_optimum() -> None:
    best = DEFAULT_CAREFUL_LOGGING_CURVE.best_level(
        harvest_volume_m3=3000.0,
        residual_asset_value=300000.0,
        base_machine_cost=100000.0,
    )

    assert best["level"] == pytest.approx(0.5)
    assert best["effective_productivity_multiplier"] == pytest.approx(0.80 * 0.90)
    assert best["care_premium"] > 0.0
    assert best["residual_damage_loss"] > 0.0


def test_public_summary_hides_exact_mapping() -> None:
    summary = DEFAULT_CAREFUL_LOGGING_CURVE.public_summary()

    assert "care_premium_per_m3_range" in summary
    assert "residual_damage_fraction_range" in summary
    assert "care_premium" not in summary
    assert "residual_damage_loss" not in summary
    assert summary["care_premium_per_m3_range"] == [0.0, 14.0]


def test_unknown_level_fails_closed() -> None:
    with pytest.raises(KeyError, match="Unknown careful-logging level"):
        DEFAULT_CAREFUL_LOGGING_CURVE.get(0.1)


def test_residual_damage_benefit_has_decreasing_marginal_returns() -> None:
    fractions = [item.residual_damage_fraction for item in DEFAULT_CAREFUL_LOGGING_CURVE.levels]
    reductions = [before - after for before, after in zip(fractions, fractions[1:])]

    assert reductions == sorted(reductions, reverse=True)
    assert len(set(reductions)) == len(reductions)


def test_care_cost_rises_as_damage_benefit_shrinks() -> None:
    rows = [
        DEFAULT_CAREFUL_LOGGING_CURVE.evaluate(
            item.level,
            harvest_volume_m3=3000.0,
            residual_asset_value=300000.0,
            base_machine_cost=100000.0,
        )
        for item in DEFAULT_CAREFUL_LOGGING_CURVE.levels
    ]
    care_costs = [row["machine_cost"] + row["care_premium"] for row in rows]
    damage_losses = [row["residual_damage_loss"] for row in rows]
    care_cost_increments = [after - before for before, after in zip(care_costs, care_costs[1:])]
    damage_reductions = [before - after for before, after in zip(damage_losses, damage_losses[1:])]

    assert care_cost_increments == sorted(care_cost_increments)
    assert damage_reductions == sorted(damage_reductions, reverse=True)
