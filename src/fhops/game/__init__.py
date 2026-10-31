"""Serious-game level and scenario-variant contracts."""

from __future__ import annotations

from .careful_logging import DEFAULT_CAREFUL_LOGGING_CURVE, CarefulLoggingCurve, CarefulLoggingLevel
from .levels import FleetOption, GameLevel, load_levels
from .operation import OperationResult, evaluate_kc_selection_cut
from .precompute import check_precompute, precompute_level
from .value import PriceSchedule
from .variants import GameChoices, build_game_scenario, fleet_penalty

__all__ = [
    "FleetOption",
    "GameChoices",
    "CarefulLoggingCurve",
    "CarefulLoggingLevel",
    "DEFAULT_CAREFUL_LOGGING_CURVE",
    "GameLevel",
    "OperationResult",
    "PriceSchedule",
    "build_game_scenario",
    "check_precompute",
    "evaluate_kc_selection_cut",
    "fleet_penalty",
    "load_levels",
    "precompute_level",
]
