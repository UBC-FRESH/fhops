"""Regression tests for multi-day marine barge cycles (FHOPS #196)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.hauling.flow import build_flow_problem, solve_flow
from fhops.scenario.io import load_scenario

FIXTURE = Path(__file__).resolve().parents[2] / "examples/hauling_marine_multiday/scenario.yaml"


def test_multiday_fixture_exposes_the_same_day_cycle_limit() -> None:
    """The fixture must fail because of the barge cycle, not a fixture error."""
    scenario = load_scenario(FIXTURE)
    problem = build_flow_problem(scenario)
    lane = problem.marine_lanes["quatsino_ladysmith_yard"]
    assert lane.barge_cycle_minutes == pytest.approx(3955.0)
    assert problem.regular_minutes == pytest.approx(510.0)
    assert lane.barge_cycle_minutes > problem.regular_minutes


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FHOPS #196: Phase I applies the 3,955-minute cycle to one day of "
        "barge fleet capacity. Remove this xfail when multi-day voyages land."
    ),
)
def test_multiday_marine_voyage_is_optimal() -> None:
    """One barge should complete the eight-day voyage and deliver the volume."""
    scenario = load_scenario(FIXTURE)
    result = solve_flow(build_flow_problem(scenario), time_limit=60)
    assert result.status == "optimal"
    assert result.cost_objective is not None
    assert result.marine_flows["water_m3"].sum() == pytest.approx(10000.0)
    assert result.barge_trips["barge_trips"].sum() == pytest.approx(1.0)
