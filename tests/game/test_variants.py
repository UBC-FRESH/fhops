"""Tests for deterministic serious-game scenario variants."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.game import GameChoices, build_game_scenario, load_levels
from fhops.game.variants import fleet_penalty, variant_fingerprint
from fhops.scenario.io import load_scenario


def test_variant_has_selected_fleet_and_deterministic_fingerprint() -> None:
    level = load_levels(Path("examples/game/levels"))[0]
    base = load_scenario(level.scenario)
    choices = GameChoices(
        fleet_counts={
            "feller_buncher": 3,
            "grapple_skidder": 2,
            "processor": 3,
            "loader": 3,
        },
        arrival_profile="hot",
        harvest_pattern="parallel",
    )

    first = build_game_scenario(base, level, choices)
    second = build_game_scenario(base, level, choices)

    assert len(first.machines) == 11
    assert variant_fingerprint(first) == variant_fingerprint(second)
    assert fleet_penalty(level, choices) > 0.0
    assert first.objective_weights == level.objective_weights


def test_staged_arrival_delays_extra_machine() -> None:
    level = load_levels(Path("examples/game/levels"))[0]
    base = load_scenario(level.scenario)
    choices = GameChoices(
        fleet_counts={
            "feller_buncher": 3,
            "grapple_skidder": 1,
            "processor": 3,
            "loader": 3,
        },
        arrival_profile="staged",
        harvest_pattern="parallel",
    )

    variant = build_game_scenario(base, level, choices)
    extra = next(machine for machine in variant.machines if machine.id.endswith("FELL-3"))
    availability = {
        entry.day: entry.available for entry in variant.calendar if entry.machine_id == extra.id
    }

    assert availability[1] == 0
    assert availability[3] == 1


def test_unknown_choice_is_rejected() -> None:
    level = load_levels(Path("examples/game/levels"))[0]
    base = load_scenario(level.scenario)
    choices = GameChoices(
        fleet_counts={role: 99 for role in level.roles},
        arrival_profile="hot",
        harvest_pattern="parallel",
    )

    with pytest.raises(ValueError, match="must be in"):
        build_game_scenario(base, level, choices)
