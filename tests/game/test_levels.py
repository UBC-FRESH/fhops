"""Tests for serious-game level manifests."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.game import load_levels


def test_levels_load_in_order_and_resolve_scenarios() -> None:
    levels = load_levels(Path("examples/game/levels"))

    assert [level.level_id for level in levels] == ["tiny7", "small21", "med42", "large84"]
    assert [level.order for level in levels] == [1, 2, 3, 4]
    assert all(level.scenario.is_file() for level in levels)
    assert all(
        level.fleet and level.arrival_profiles and level.harvest_patterns for level in levels
    )


def test_fleet_penalty_increases_and_spot_slot_is_expensive() -> None:
    tiny7 = load_levels(Path("examples/game/levels"))[0]
    feller = next(option for option in tiny7.fleet if option.role == "feller_buncher")

    assert feller.penalty(feller.owned) == 0.0
    assert feller.penalty(feller.owned + 1) == pytest.approx(
        feller.unit_cost + feller.spot_surcharge
    )
    if feller.owned + 2 <= feller.maximum:
        assert feller.penalty(feller.owned + 2) == pytest.approx(
            feller.unit_cost + 2.0 * feller.unit_cost + feller.spot_surcharge
        )
