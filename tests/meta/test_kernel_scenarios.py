"""Scenario-level replay gates for the kernel-backed FHOPS solvers."""

from __future__ import annotations

import pytest

from fhops.optimization.heuristics.common import evaluate_assignments
from fhops.optimization.meta import solve_kernel_ils, solve_kernel_sa, solve_kernel_tabu
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario


@pytest.mark.parametrize(
    ("solver", "kwargs"),
    [
        (solve_kernel_sa, {"iters": 25, "seed": 11}),
        (solve_kernel_tabu, {"iters": 25, "seed": 11, "samples": 4}),
        (solve_kernel_ils, {"iters": 8, "seed": 11, "perturbation": 2}),
    ],
)
def test_tiny7_kernel_results_replay_exactly(solver, kwargs) -> None:
    """Every kernel path returns an assignment table that replays to its reported score."""
    pb = Problem.from_scenario(load_scenario("examples/tiny7/scenario.yaml"))
    result = solver(pb, **kwargs)
    assert result["objective"] == pytest.approx(evaluate_assignments(pb, result["assignments"]))
    assert result["meta"]["greedy_objective"] is not None
    assert result["meta"]["objective_delta_vs_greedy"] == pytest.approx(
        result["objective"] - result["meta"]["greedy_objective"]
    )
