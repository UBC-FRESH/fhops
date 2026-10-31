"""Tests for stand-scale finite precompute and scoring bounds."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.game.scoring import ScoreBounds, normalize_score
from fhops.game.stand_precompute import (
    GameStandPrecomputeError,
    check_stand_precompute,
    precompute_stand_level,
)

LEVEL = Path("examples/game/levels/kc_57254551/level.yaml")


def _fake_eval(
    scenario_path: Path,
    *,
    price_path: Path,
    care_level: float,
    form_factor: float,
    log_length_m: float,
    sawlog_min_dbh_cm: float,
    road_extension_m: float,
    machine_ids: dict[str, object],
) -> dict[str, float]:
    del scenario_path, price_path, form_factor, sawlog_min_dbh_cm, road_extension_m, machine_ids
    return {"net_profit": 1000.0 - 100.0 * care_level + 10.0 * log_length_m}


def test_score_normalization() -> None:
    bounds = ScoreBounds(best_net_profit=200.0, worst_net_profit=100.0)

    assert normalize_score(100.0, bounds) == 0.0
    assert normalize_score(200.0, bounds) == 100.0
    assert normalize_score(150.0, bounds) == 50.0
    assert normalize_score(999.0, bounds) == 100.0
    assert normalize_score(-999.0, bounds) == 0.0


def test_precompute_covers_full_menu() -> None:
    payload = precompute_stand_level(LEVEL, evaluate_fn=_fake_eval)

    assert payload["completeness"]["complete"] is True
    assert payload["completeness"]["combination_count"] == 20
    assert payload["bounds"]["best_net_profit"] > payload["bounds"]["worst_net_profit"]
    check_stand_precompute(LEVEL, payload)


def test_precompute_fails_closed_on_missing_variant() -> None:
    payload = precompute_stand_level(LEVEL, evaluate_fn=_fake_eval)
    payload["variants"].pop()

    with pytest.raises(GameStandPrecomputeError, match="precompute menu mismatch"):
        check_stand_precompute(LEVEL, payload)
