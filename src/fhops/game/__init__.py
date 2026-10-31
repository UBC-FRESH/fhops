"""Serious-game level and scenario-variant contracts."""

from __future__ import annotations

from .careful_logging import DEFAULT_CAREFUL_LOGGING_CURVE, CarefulLoggingCurve, CarefulLoggingLevel
from .levels import FleetOption, GameLevel, load_levels
from .operation import OperationResult, evaluate_kc_selection_cut
from .precompute import check_precompute, precompute_level
from .scoring import ScoreBounds, normalize_score
from .stand_precompute import (
    GameStandPrecomputeError,
    StandChoices,
    check_stand_precompute,
    load_stand_precompute,
    precompute_stand_level,
    write_stand_precompute,
)
from .state import GameStateError, LevelAttempt, TeamState, TournamentSession
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
    "GameStandPrecomputeError",
    "GameStateError",
    "LevelAttempt",
    "ScoreBounds",
    "StandChoices",
    "TeamState",
    "build_game_scenario",
    "check_stand_precompute",
    "check_precompute",
    "evaluate_kc_selection_cut",
    "fleet_penalty",
    "load_levels",
    "load_stand_precompute",
    "TournamentSession",
    "normalize_score",
    "precompute_level",
    "precompute_stand_level",
    "write_stand_precompute",
]
