"""Private legacy day-level MIP solve path (``_solve_legacy_mip``; #124, retired by #127).

Same result policy as the operational driver (#115): infeasible models, time limits without an
incumbent and solver errors are reported (``has_solution``, ``outcome``, ``solver_error``) instead
of raised. Since #127 no public entry point uses this path (``solve_mip``, ``fhops solve-mip`` and
``fhops benchmark`` delegate to the operational MILP; see ``tests/test_legacy_mip_retirement.py``);
these tests keep the legacy infeasibility finding reproducible.
"""

from __future__ import annotations

from types import SimpleNamespace

import pyomo.environ as pyo
import pytest
from pyomo.common.errors import ApplicationError

import fhops.optimization.mip.highs_driver as hd
from fhops.optimization.mip.builder import build_model
from fhops.optimization.mip.highs_driver import ASSIGNMENT_COLUMNS, SolverUnavailable
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

solve_legacy_mip = hd._solve_legacy_mip
pytestmark = pytest.mark.filterwarnings(
    "ignore::fhops.optimization.mip.deprecation.LegacyMipDeprecationWarning"
)

REGRESSION = "tests/fixtures/regression/regression.yaml"
TINY7 = "examples/tiny7/scenario.yaml"
HIGHS_DRIVERS = ["auto", "highs-appsi", "highs-exec"]
# Assignments returned by FHOPS 1.0.0 for the regression fixture with its ``ground_sequence``
# system registered in the YAML (#129; before, the system was unregistered and 1.0.0/b73376d
# returned F1-B1-d1, F1-B2-d4, P1-B2-d4 with production 4/0/4).
REGRESSION_ASSIGNMENTS = {
    "machine_id": ["F1", "F1", "P1", "F1", "P1", "F1", "P1"],
    "block_id": ["B1", "B1", "B1", "B1", "B1", "B2", "B2"],
    "day": [1, 2, 2, 3, 3, 4, 4],
    "shift_id": ["S1"] * 7,
    "assigned": [1] * 7,
    "production": [4.0, 0.0, 0.0, 0.0, 0.0, 4.0, 0.0],
}


@pytest.fixture(scope="module")
def regression() -> Problem:
    return Problem.from_scenario(load_scenario(REGRESSION))


@pytest.fixture(scope="module")
def tiny7() -> Problem:
    return Problem.from_scenario(load_scenario(TINY7))


def _assert_empty(result) -> None:
    assert result["has_solution"] is False
    assert result["objective"] is None
    assert list(result["assignments"].columns) == ASSIGNMENT_COLUMNS
    assert result["assignments"].empty


@pytest.mark.parametrize("driver", HIGHS_DRIVERS)
def test_normal_solve_is_unchanged(regression, driver) -> None:
    result = solve_legacy_mip(regression, time_limit=60, driver=driver)
    assert result["objective"] == 8.0
    assert result["has_solution"] is True
    assert result["outcome"] == "optimal"
    assert result["termination_condition"] == "optimal"
    assert result["solver_error"] is None
    assert result["warnings"] == []
    assignments = result["assignments"]
    assert list(assignments.columns) == ASSIGNMENT_COLUMNS
    assert assignments.reset_index(drop=True).to_dict("list") == REGRESSION_ASSIGNMENTS


@pytest.mark.parametrize("driver", HIGHS_DRIVERS)
def test_infeasible_tiny7_is_reported_not_raised(tiny7, driver) -> None:
    # The legacy MIP's loader buffer (``prod_loader(≤s) <= prod_prereq(<s) - batch``) cannot hold
    # in the first shift, so every scenario with a loader batch volume (tiny7, small21, med42) is
    # infeasible; FHOPS 1.0.0 raised RuntimeError / NoFeasibleSolutionError here.
    result = solve_legacy_mip(tiny7, time_limit=60, driver=driver)
    _assert_empty(result)
    assert result["outcome"] == "infeasible"
    assert result["solver_error"] is None


@pytest.mark.parametrize("driver", HIGHS_DRIVERS)
def test_forced_infeasible_model(regression, driver, monkeypatch) -> None:
    def _infeasible(pb):
        model = build_model(pb)
        model.force_infeasible = pyo.Constraint(expr=model.prod["F1", "B1", (1, "S1")] >= 1e6)
        return model

    monkeypatch.setattr(hd, "build_model", _infeasible)
    result = solve_legacy_mip(regression, time_limit=60, driver=driver)
    _assert_empty(result)
    assert result["outcome"] == "infeasible"
    assert result["solver_error"] is None


@pytest.mark.parametrize("driver", HIGHS_DRIVERS)
def test_time_limit_without_incumbent(regression, driver) -> None:
    result = solve_legacy_mip(regression, time_limit=0, driver=driver)
    _assert_empty(result)
    assert result["outcome"] == "no_solution"
    assert result["termination_condition"] == "maxTimeLimit"
    assert result["solver_error"] is None


@pytest.mark.parametrize("driver", ["highs-appsi", "highs-exec"])
def test_highs_option_error_is_reported_as_solver_error(regression, driver, monkeypatch) -> None:
    # The first solve initialises HiGHS' global scheduler; a different thread count afterwards
    # makes HiGHS refuse to run. Before #124 the APPSI path raised "A feasible solution was not
    # found" (i.e. reported a solver failure as infeasibility).
    assert solve_legacy_mip(regression, driver=driver)["outcome"] == "optimal"
    make_appsi, make_exec = hd._try_appsi_highs, hd._try_exec_highs

    def _bad_appsi():
        solver = make_appsi()
        solver.highs_options = {"threads": 997}
        return solver

    def _bad_exec():
        solver = make_exec()
        solver.options["threads"] = 997
        return solver

    monkeypatch.setattr(hd, "_try_appsi_highs", _bad_appsi)
    monkeypatch.setattr(hd, "_try_exec_highs", _bad_exec)
    result = solve_legacy_mip(regression, driver=driver)
    _assert_empty(result)
    assert result["outcome"] == "error"
    assert "ERROR" in result["solver_error"]
    assert "threads" in result["solver_error"]


def test_solver_exception_is_reported_as_solver_error(regression, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Crashing:
        options: dict[str, object] = {}

        def solve(self, model, **kwargs):
            captured.update(kwargs)
            raise ApplicationError("solver executable crashed")

    monkeypatch.setattr(hd, "_try_exec_highs", lambda: _Crashing())
    result = solve_legacy_mip(regression, driver="highs-exec")
    _assert_empty(result)
    assert result["outcome"] == "error"
    assert "solver executable crashed" in result["solver_error"]
    assert captured["load_solutions"] is False


class _FakeAppsi:
    """APPSI-like solver whose solve fails or reports no solution."""

    def __init__(self, *, raises: bool) -> None:
        self.raises = raises
        self.config = SimpleNamespace(time_limit=None, verbosity=0)

    def solve(self, model):
        assert self.config.load_solution is False
        if self.raises:
            raise RuntimeError("license expired")
        return SimpleNamespace(
            termination_condition=SimpleNamespace(name="infeasible"),
            best_feasible_objective=None,
        )


def test_auto_falls_back_to_highs_when_gurobi_fails(regression, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_try_appsi_gurobi", lambda: _FakeAppsi(raises=True))
    monkeypatch.setattr(hd, "_try_exec_gurobi", lambda: None)
    result = solve_legacy_mip(regression, driver="auto")
    assert result["outcome"] == "optimal"
    assert result["objective"] == 8.0
    assert any("license expired" in note and "HiGHS" in note for note in result["warnings"])


def test_explicit_gurobi_failure_is_returned(regression, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_try_appsi_gurobi", lambda: _FakeAppsi(raises=True))
    monkeypatch.setattr(hd, "_try_exec_gurobi", lambda: None)
    result = solve_legacy_mip(regression, driver="gurobi")
    _assert_empty(result)
    assert result["outcome"] == "error"
    assert "license expired" in result["solver_error"]


def test_gurobi_infeasible_is_not_an_error(regression, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_try_appsi_gurobi", lambda: _FakeAppsi(raises=False))
    result = solve_legacy_mip(regression, driver="gurobi-appsi")
    _assert_empty(result)
    assert result["outcome"] == "infeasible"
    assert result["solver_error"] is None


def test_missing_solver_still_raises_unavailable(regression, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_try_appsi_gurobi", lambda: None)
    monkeypatch.setattr(hd, "_try_exec_gurobi", lambda: None)
    monkeypatch.setattr(hd, "_try_exec_highs", lambda: None)
    for driver in ("gurobi", "gurobi-appsi", "gurobi-direct", "highs-exec"):
        with pytest.raises(SolverUnavailable):
            solve_legacy_mip(regression, driver=driver)
    with pytest.raises(ValueError, match="Unknown MIP driver"):
        solve_legacy_mip(regression, driver="cplex")
