"""Legacy day-level MIP driver (``solve_mip``, ``fhops solve-mip``, ``fhops benchmark``; #124).

Same result policy as the operational driver (#115): infeasible models, time limits without an
incumbent and solver errors are reported (``has_solution``, ``outcome``, ``solver_error``) instead
of raised; normal solves are unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pyomo.environ as pyo
import pytest
from pyomo.common.errors import ApplicationError

import fhops.optimization.mip.highs_driver as hd
from fhops.cli.main import app
from fhops.optimization.mip import solve_mip
from fhops.optimization.mip.builder import build_model
from fhops.optimization.mip.highs_driver import ASSIGNMENT_COLUMNS, SolverUnavailable
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from tests.cli import CliRunner, cli_text

REGRESSION = "tests/fixtures/regression/regression.yaml"
TINY7 = "examples/tiny7/scenario.yaml"
HIGHS_DRIVERS = ["auto", "highs-appsi", "highs-exec"]
# Assignments returned by FHOPS 1.0.0 and by b73376d (before #124) for the regression fixture.
REGRESSION_ASSIGNMENTS = {
    "machine_id": ["F1", "F1", "P1"],
    "block_id": ["B1", "B2", "B2"],
    "day": [1, 4, 4],
    "shift_id": ["S1", "S1", "S1"],
    "assigned": [1, 1, 1],
    "production": [4.0, 0.0, 4.0],
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
    result = solve_mip(regression, time_limit=60, driver=driver)
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
    result = solve_mip(tiny7, time_limit=60, driver=driver)
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
    result = solve_mip(regression, time_limit=60, driver=driver)
    _assert_empty(result)
    assert result["outcome"] == "infeasible"
    assert result["solver_error"] is None


@pytest.mark.parametrize("driver", HIGHS_DRIVERS)
def test_time_limit_without_incumbent(regression, driver) -> None:
    result = solve_mip(regression, time_limit=0, driver=driver)
    _assert_empty(result)
    assert result["outcome"] == "no_solution"
    assert result["termination_condition"] == "maxTimeLimit"
    assert result["solver_error"] is None


@pytest.mark.parametrize("driver", ["highs-appsi", "highs-exec"])
def test_highs_option_error_is_reported_as_solver_error(regression, driver, monkeypatch) -> None:
    # The first solve initialises HiGHS' global scheduler; a different thread count afterwards
    # makes HiGHS refuse to run. Before #124 the APPSI path raised "A feasible solution was not
    # found" (i.e. reported a solver failure as infeasibility).
    assert solve_mip(regression, driver=driver)["outcome"] == "optimal"
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
    result = solve_mip(regression, driver=driver)
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
    result = solve_mip(regression, driver="highs-exec")
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
    result = solve_mip(regression, driver="auto")
    assert result["outcome"] == "optimal"
    assert result["objective"] == 8.0
    assert any("license expired" in note and "HiGHS" in note for note in result["warnings"])


def test_explicit_gurobi_failure_is_returned(regression, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_try_appsi_gurobi", lambda: _FakeAppsi(raises=True))
    monkeypatch.setattr(hd, "_try_exec_gurobi", lambda: None)
    result = solve_mip(regression, driver="gurobi")
    _assert_empty(result)
    assert result["outcome"] == "error"
    assert "license expired" in result["solver_error"]


def test_gurobi_infeasible_is_not_an_error(regression, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_try_appsi_gurobi", lambda: _FakeAppsi(raises=False))
    result = solve_mip(regression, driver="gurobi-appsi")
    _assert_empty(result)
    assert result["outcome"] == "infeasible"
    assert result["solver_error"] is None


def test_missing_solver_still_raises_unavailable(regression, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_try_appsi_gurobi", lambda: None)
    monkeypatch.setattr(hd, "_try_exec_gurobi", lambda: None)
    monkeypatch.setattr(hd, "_try_exec_highs", lambda: None)
    for driver in ("gurobi", "gurobi-appsi", "gurobi-direct", "highs-exec"):
        with pytest.raises(SolverUnavailable):
            solve_mip(regression, driver=driver)
    with pytest.raises(ValueError, match="Unknown MIP driver"):
        solve_mip(regression, driver="cplex")


# --- CLI ----------------------------------------------------------------------------------------


def test_cli_solve_mip_success(tmp_path) -> None:
    out = tmp_path / "mip.csv"
    result = CliRunner().invoke(app, ["solve-mip", REGRESSION, "--out", str(out)])
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "MIP outcome=optimal" in text
    assert "objective=8.000" in text
    assert "No feasible solution" not in text
    assert len(pd.read_csv(out)) == 3


def test_cli_solve_mip_infeasible_exits_zero(tmp_path) -> None:
    out = tmp_path / "mip.csv"
    result = CliRunner().invoke(app, ["solve-mip", TINY7, "--out", str(out)])
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "MIP outcome=infeasible" in text
    assert "objective=n/a" in text
    assert "the model is infeasible" in text
    frame = pd.read_csv(out)
    assert frame.empty and list(frame.columns) == ASSIGNMENT_COLUMNS


def _fake_solve_mip(payload: dict):
    def _solve(pb, **kwargs):
        base = {
            "objective": None,
            "assignments": pd.DataFrame(columns=ASSIGNMENT_COLUMNS),
            "has_solution": False,
            "solver_status": "unknown",
            "termination_condition": "unknown",
            "solver_error": None,
            "warnings": [],
        }
        base.update(payload)
        return base

    return _solve


def test_cli_solve_mip_time_limit_without_incumbent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "fhops.cli.main.solve_mip",
        _fake_solve_mip({"outcome": "no_solution", "termination_condition": "maxTimeLimit"}),
    )
    result = CliRunner().invoke(app, ["solve-mip", REGRESSION, "--out", str(tmp_path / "m.csv")])
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "outcome=no_solution" in text
    assert "stopped without a feasible solution" in text


def test_cli_solve_mip_solver_error_exits_one(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "fhops.cli.main.solve_mip",
        _fake_solve_mip(
            {
                "outcome": "error",
                "solver_error": "ERROR:   Option 'threads' is set to 997",
                "warnings": ["Gurobi failed (x); falling back to HiGHS (driver=auto)."],
            }
        ),
    )
    out = tmp_path / "m.csv"
    result = CliRunner().invoke(app, ["solve-mip", REGRESSION, "--out", str(out)])
    text = cli_text(result)
    assert result.exit_code == 1, text
    assert "outcome=error" in text
    assert "Solver error" in text
    assert "Warning:" in text
    assert "infeasible" not in text
    assert pd.read_csv(out).empty


def test_cli_solve_mip_unavailable_and_bad_driver(monkeypatch, tmp_path) -> None:
    out = str(tmp_path / "m.csv")
    result = CliRunner().invoke(app, ["solve-mip", REGRESSION, "--out", out, "--driver", "nope"])
    assert result.exit_code == 2, cli_text(result)

    def _unavailable(pb, **kwargs):
        raise SolverUnavailable("HiGHS solver not available")

    monkeypatch.setattr("fhops.cli.main.solve_mip", _unavailable)
    result = CliRunner().invoke(app, ["solve-mip", REGRESSION, "--out", out])
    text = cli_text(result)
    assert result.exit_code == 1, text
    assert "Solver unavailable" in text


def test_cli_benchmark_handles_missing_mip_solution(tmp_path) -> None:
    result = CliRunner().invoke(
        app, ["benchmark", TINY7, "--out-dir", str(tmp_path), "--iters", "50"]
    )
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "MIP obj=n/a (outcome=infeasible)" in text
    assert "MIP metrics skipped" in text
    assert "SA metrics:" in text
    assert pd.read_csv(tmp_path / "mip_solution.csv").empty
    assert not pd.read_csv(tmp_path / "sa_solution.csv").empty


def test_cli_benchmark_solver_error_exits_one(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "fhops.cli.main.solve_mip",
        _fake_solve_mip({"outcome": "error", "solver_error": "solver exploded"}),
    )
    result = CliRunner().invoke(
        app, ["benchmark", REGRESSION, "--out-dir", str(tmp_path), "--iters", "20"]
    )
    text = cli_text(result)
    assert result.exit_code == 1, text
    assert "MIP solver error" in text
    assert "SA metrics:" in text
