"""Serious-game level and scenario-variant contracts."""

from __future__ import annotations

from .levels import FleetOption, GameLevel, load_levels
from .precompute import check_precompute, precompute_level
from .variants import GameChoices, build_game_scenario, fleet_penalty

__all__ = [
    "FleetOption",
    "GameChoices",
    "GameLevel",
    "build_game_scenario",
    "check_precompute",
    "fleet_penalty",
    "load_levels",
    "precompute_level",
]
