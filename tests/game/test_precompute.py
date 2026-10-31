"""Tests for exact serious-game precompute contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from fhops.game import check_precompute, load_levels, precompute_level
from fhops.game.precompute import GamePrecomputeError, enumerate_choices
from fhops.scenario.contract import Problem


def _toy_level():
    tiny7 = load_levels(Path("examples/game/levels"))[0]
    fleet = tuple(
        replace(option, maximum=option.owned) if option.role != "feller_buncher" else option
        for option in tiny7.fleet
    )
    return replace(
        tiny7,
        fleet=fleet,
        arrival_profiles=("hot", "staged"),
        harvest_patterns=("parallel",),
    )


def _fake_solver(problem: Problem) -> dict[str, Any]:
    return {
        "outcome": "optimal",
        "objective": float(len(problem.scenario.machines) * 10),
        "production": float(len(problem.scenario.machines)),
    }


def test_enumerate_choices_is_finite_and_deterministic() -> None:
    level = _toy_level()
    first = list(enumerate_choices(level))
    second = list(enumerate_choices(level))

    assert len(first) == 4
    assert [choice.fleet_counts["feller_buncher"] for choice in first] == [2, 2, 3, 3]
    assert first == second


def test_precompute_excludes_infeasible_and_checks_coverage() -> None:
    level = _toy_level()
    payload = precompute_level(level, solve_fn=_fake_solver)

    assert payload["completeness"]["complete"] is True
    assert payload["completeness"]["feasible_count"] == 4
    assert (
        payload["bounds"]["best_adjusted_objective"]
        >= payload["bounds"]["worst_adjusted_objective"]
    )
    check_precompute(level, payload)


def test_precompute_fails_closed_on_nonoptimal_result() -> None:
    level = _toy_level()

    def bad_solver(_: Problem) -> dict[str, Any]:
        return {"outcome": "feasible", "objective": 1.0, "production": 1.0}

    with pytest.raises(GamePrecomputeError, match="expected optimal"):
        precompute_level(level, solve_fn=bad_solver)
