"""Operational-MILP driver robustness (#115): no exceptions for missing solutions, solver errors
surfaced as errors, warm-start acceptance inference, clean exports, and the tiny7 regression."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pandas as pd
import pyomo.environ as pyo
import pytest
from pyomo.common.errors import ApplicationError

import fhops.model.milp.driver as driver
from fhops.cli.main import app
from fhops.evaluation.playback import run_playback
from fhops.model.milp.driver import ASSIGNMENT_COLUMNS, solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from tests.cli import CliRunner, cli_text

TINY7 = "examples/tiny7/scenario.yaml"
# Since #125 the tiny7 landings (capacity 1) are a hard per-slot limit (ω_land = 0); the
# objective before was 4388.082752 with the per-day, free landing slack.
TINY7_OBJECTIVE = 279.79603600008943


@pytest.fixture(scope="module")
def tiny7():
    pb = Problem.from_scenario(load_scenario(TINY7))
    return pb, build_operational_problem(pb)


def _assert_empty_result(result: dict) -> None:
    assert result["has_solution"] is False
    assert result["objective"] is None
    assert result["production"] == 0.0
    assert list(result["assignments"].columns) == ASSIGNMENT_COLUMNS
    assert result["assignments"].empty


def test_time_limit_without_incumbent_returns_none(tiny7) -> None:
    _, ctx = tiny7
    result = solve_operational_milp(ctx.bundle, solver="highs", time_limit=1e-6)
    _assert_empty_result(result)
    assert result["outcome"] == "no_solution"
    assert result["termination_condition"] == "maxTimeLimit"
    assert result["solver_error"] is None


def test_infeasible_model_returns_status_instead_of_raising(tiny7, monkeypatch) -> None:
    _, ctx = tiny7

    def _infeasible(bundle):
        model = build_operational_model(bundle)
        model.force_infeasible = pyo.Constraint(expr=model.leftover["B01"] <= -1.0)
        return model

    monkeypatch.setattr(driver, "build_operational_model", _infeasible)
    result = solve_operational_milp(ctx.bundle, solver="highs", time_limit=30)
    _assert_empty_result(result)
    assert result["outcome"] == "infeasible"
    assert result["solver_error"] is None


def test_highs_option_error_is_reported_as_solver_error(tiny7) -> None:
    _, ctx = tiny7
    # The first solve initialises HiGHS' global scheduler with the default thread count; asking
    # for a different count afterwards makes HiGHS refuse to run (audit opt3.py). v1.0.0/1.0.0
    # raised NoFeasibleSolutionError ("infeasible"); now the HiGHS ERROR line is surfaced.
    assert solve_operational_milp(ctx.bundle, solver="highs")["outcome"] == "optimal"
    result = solve_operational_milp(ctx.bundle, solver="highs", solver_options={"threads": 997})
    _assert_empty_result(result)
    assert result["outcome"] == "error"
    assert "threads" in result["solver_error"]
    assert "ERROR" in result["solver_error"]


class _RaisingSolver:
    def available(self, exception_flag: bool = True) -> bool:
        return True

    def __init__(self) -> None:
        self.options: dict[str, object] = {}
        self.kwargs: dict[str, object] = {}

    def solve(self, model, **kwargs):
        self.kwargs = kwargs
        raise ApplicationError("solver executable crashed")


def test_solver_exception_is_reported_as_solver_error(tiny7, monkeypatch) -> None:
    _, ctx = tiny7
    solver = _RaisingSolver()
    monkeypatch.setattr(driver, "SolverFactory", lambda _name: solver)
    result = solve_operational_milp(ctx.bundle, solver="cbc")
    _assert_empty_result(result)
    assert result["outcome"] == "error"
    assert "solver executable crashed" in result["solver_error"]
    assert solver.kwargs["load_solutions"] is False


def test_legacy_plugin_results_without_solution_do_not_raise(tiny7, monkeypatch) -> None:
    _, ctx = tiny7
    captured: dict[str, object] = {}

    class _NoSolution:
        options: dict[str, object] = {}

        def solve(self, model, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                solver=SimpleNamespace(status="aborted", termination_condition="maxTimeLimit"),
                problem=SimpleNamespace(lower_bound=None, upper_bound=None),
                solution=[],
            )

    monkeypatch.setattr(driver, "SolverFactory", lambda _name: _NoSolution())
    result = solve_operational_milp(ctx.bundle, solver="cbc", time_limit=5)
    _assert_empty_result(result)
    assert result["outcome"] == "no_solution"
    assert captured["load_solutions"] is False


def test_extracted_production_has_no_negative_zero() -> None:
    model = pyo.ConcreteModel()
    model.x = pyo.Var([("M1", "B1", 1, "S1")], domain=pyo.Binary)
    model.prod = pyo.Var([("M1", "B1", 1, "S1")])
    model.x["M1", "B1", 1, "S1"].set_value(1)
    model.prod["M1", "B1", 1, "S1"].set_value(-0.0)
    frame = driver._extract_assignments(model)
    value = frame["production"].iloc[0]
    assert value == 0.0 and math.copysign(1.0, value) == 1.0
    model.prod["M1", "B1", 1, "S1"].set_value(-1e-12)
    assert math.copysign(1.0, driver._extract_assignments(model)["production"].iloc[0]) == 1.0


def test_warm_start_acceptance_inferred_when_highs_log_is_silent(tiny7, monkeypatch) -> None:
    _, ctx = tiny7
    cold = solve_operational_milp(ctx.bundle, solver="highs", context=ctx)
    monkeypatch.setattr(driver, "_parse_highs_start_log", lambda _lines: (None, []))
    warm = solve_operational_milp(
        ctx.bundle,
        solver="highs",
        time_limit=30,
        incumbent_assignments=cold["assignments"],
        context=ctx,
    )
    assert warm["warm_start"]["method"] == "appsi_highs"
    assert warm["warm_start"]["accepted"] is True
    assert warm["warm_start"]["acceptance"] == "inferred"
    assert warm["objective"] == pytest.approx(cold["objective"], abs=1e-6)


def test_seed_inference_requires_feasible_seed_or_identical_assignment(tiny7) -> None:
    _, ctx = tiny7
    model = build_operational_model(ctx.bundle)
    for var in model.component_data_objects(pyo.Var):
        var.set_value(0)
    seed = driver._snapshot_seed(model)
    # All-zero seed violates the block balance (leftover = 0), so it is not feasible ...
    assert driver._seed_is_feasible(model, seed) is False
    # ... but a returned solution with identical x values still counts as the seed.
    assert driver._seed_accepted(model, seed) is True
    first = next(iter(model.x))
    model.x[first].set_value(1)
    assert driver._seed_accepted(model, seed) is False
    # The feasibility check restores the loaded (returned) values.
    assert model.x[first].value == 1


# --- tiny7 regression ---------------------------------------------------------------------------


def test_tiny7_milp_objective_feasibility_and_replay(tiny7, monkeypatch) -> None:
    """tiny7 reference: objective, constraint feasibility and playback consistency.

    The tiny7 MILP has several optimal assignment tables (see
    ``test_tiny7_milp_has_alternative_optima``), so the regression checks the objective, the
    feasibility of the loaded solution and its replay instead of exact assignments.
    """

    pb, ctx = tiny7
    captured: dict[str, pyo.ConcreteModel] = {}

    def _capture(bundle):
        captured["model"] = build_operational_model(bundle)
        return captured["model"]

    monkeypatch.setattr(driver, "build_operational_model", _capture)
    result = solve_operational_milp(ctx.bundle, solver="highs", context=ctx)
    assert result["outcome"] == "optimal"
    assert result["objective"] == pytest.approx(TINY7_OBJECTIVE, abs=1e-6)
    assert driver._max_violation(captured["model"]) <= 1e-6
    frame = result["assignments"]
    assert (frame["production"] >= 0).all()
    playback = run_playback(pb, frame)
    assert not [r for r in playback.records if r.metadata.get("sequencing_violation")]
    terminal = {"loader"}
    planned = frame[frame.machine_id.map(ctx.bundle.machine_roles).isin(terminal)][
        "production"
    ].sum()
    assert playback.delivered_total == pytest.approx(planned, abs=1e-5)


def test_tiny7_milp_has_alternative_optima(tiny7) -> None:
    _, ctx = tiny7
    result = solve_operational_milp(ctx.bundle, solver="highs")
    chosen = {
        (row.machine_id, row.block_id, int(row.day), row.shift_id)
        for row in result["assignments"].itertuples()
        if row.assigned
    }
    model = build_operational_model(ctx.bundle)
    # No-good cut: forbid exactly the returned assignment table.
    model.no_good = pyo.Constraint(
        expr=sum(model.x[key] for key in chosen)
        - sum(var for key, var in model.x.items() if key not in chosen)
        <= len(chosen) - 1
    )
    results = pyo.SolverFactory("highs").solve(model, load_solutions=False)
    model.solutions.load_from(results)
    assert pyo.value(model.objective) == pytest.approx(TINY7_OBJECTIVE, abs=1e-6)


# --- CLI messages -------------------------------------------------------------------------------


def _fake_solver(payload: dict):
    def _solve(bundle, **kwargs):
        base = {
            "production": 0.0,
            "assignments": pd.DataFrame(columns=ASSIGNMENT_COLUMNS),
            "warnings": [],
        }
        base.update(payload)
        return base

    return _solve


def _invoke(monkeypatch, tmp_path, payload: dict):
    monkeypatch.setattr("fhops.cli.main.solve_operational_milp", _fake_solver(payload))
    out = tmp_path / "plan.csv"
    result = CliRunner().invoke(app, ["solve-mip-operational", TINY7, "--out", str(out)])
    return result, cli_text(result), out


def test_cli_reports_empty_incumbent_consistently(monkeypatch, tmp_path) -> None:
    # A time-limited incumbent that assigns nothing (objective = -Σ W) used to print the
    # objective and then "No feasible assignment returned".
    result, text, out = _invoke(
        monkeypatch,
        tmp_path,
        {
            "objective": -4414.702752,
            "has_solution": True,
            "outcome": "feasible",
            "solver_status": "aborted",
            "termination_condition": "maxTimeLimit",
            "solver_error": None,
        },
    )
    assert result.exit_code == 0, text
    assert "outcome=feasible" in text
    assert "objective=-4414.702752" in text
    assert "assigns no machines" in text
    assert "No feasible" not in text
    assert out.exists()


def test_cli_reports_missing_solution_without_objective(monkeypatch, tmp_path) -> None:
    result, text, out = _invoke(
        monkeypatch,
        tmp_path,
        {
            "objective": None,
            "has_solution": False,
            "outcome": "no_solution",
            "solver_status": "aborted",
            "termination_condition": "maxTimeLimit",
            "solver_error": None,
            "warnings": ["lock (X, B1, day 1, shift *) ignored: unknown machine or block"],
        },
    )
    assert result.exit_code == 0, text
    assert "objective=n/a" in text
    assert "No feasible solution" in text
    assert "Warning:" in text
    assert pd.read_csv(out).empty


def test_cli_exits_nonzero_on_solver_error(monkeypatch, tmp_path) -> None:
    result, text, _ = _invoke(
        monkeypatch,
        tmp_path,
        {
            "objective": None,
            "has_solution": False,
            "outcome": "error",
            "solver_status": "unknown",
            "termination_condition": "unknown",
            "solver_error": "ERROR:   Option 'threads' is set to 997",
        },
    )
    assert result.exit_code == 1, text
    assert "outcome=error" in text
    assert "Solver error" in text
    assert "infeasible" not in text
