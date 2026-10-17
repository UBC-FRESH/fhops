"""Solver failures never escape the operational MILP drivers; ``auto`` falls back to HiGHS (#139).

Gurobi raises ``gurobipy.GurobiError`` from ``solve`` for a missing licence or a model larger
than the pip size-limited licence allows. Every driver path reports such exceptions as
``outcome="error"`` with ``solver_error``; ``solver="auto"`` (and the legacy ``driver="auto"``)
retries with HiGHS and warns.
"""

from __future__ import annotations

import warnings

import pytest

import fhops.model.milp.driver as milp_driver
import fhops.optimization.mip.highs_driver as hd
from fhops.model.milp.driver import MilpSolverFallbackWarning, solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.mip import LegacyMipDeprecationWarning, solve_mip
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

TINY7_OBJECTIVE = 279.796036


class FakeGurobiError(Exception):
    """Stand-in for ``gurobipy.GurobiError`` (an ``Exception``, not a ``RuntimeError``)."""


class _RaisingSolver:
    """Legacy-plugin look-alike whose ``solve`` raises like a size-limited Gurobi licence."""

    def __init__(self, *, fail_on_options: bool = False) -> None:
        self.options = _FailingOptions() if fail_on_options else {}

    def available(self, exception_flag: bool = True) -> bool:
        return True

    def warm_start_capable(self) -> bool:
        return True

    def solve(self, model, **kwargs):
        raise FakeGurobiError("Model too large for size-limited license")


class _FailingOptions(dict):
    def __setitem__(self, key, value):
        raise FakeGurobiError(f"Unknown parameter '{key}'")


@pytest.fixture(scope="module")
def tiny7_ctx():
    return build_operational_problem(
        Problem.from_scenario(load_scenario("examples/tiny7/scenario.yaml"))
    )


def _patch_gurobi(monkeypatch, solver_or_none) -> None:
    real_factory = milp_driver.SolverFactory

    def factory(name, *args, **kwargs):
        if name in {"gurobi", "appsi_gurobi", "gurobi_direct"}:
            if solver_or_none is None:
                return _Unavailable()
            return solver_or_none
        return real_factory(name, *args, **kwargs)

    monkeypatch.setattr(milp_driver, "SolverFactory", factory)


class _Unavailable:
    options: dict = {}

    def available(self, exception_flag: bool = True) -> bool:
        return False


def test_gurobi_exception_is_reported_not_raised(tiny7_ctx, monkeypatch) -> None:
    _patch_gurobi(monkeypatch, _RaisingSolver())
    result = solve_operational_milp(tiny7_ctx.bundle, solver="gurobi", time_limit=10)
    assert result["outcome"] == "error"
    assert result["has_solution"] is False
    assert result["solver_error"] == "FakeGurobiError: Model too large for size-limited license"
    assert result["assignments"].empty
    assert result["solver"] == "gurobi"


def test_solver_option_failure_is_reported_not_raised(tiny7_ctx, monkeypatch) -> None:
    _patch_gurobi(monkeypatch, _RaisingSolver(fail_on_options=True))
    result = solve_operational_milp(tiny7_ctx.bundle, solver="gurobi", time_limit=10, gap=0.01)
    assert result["outcome"] == "error"
    assert result["solver_error"].startswith("FakeGurobiError: Unknown parameter")


def test_auto_falls_back_to_highs_with_a_warning(tiny7_ctx, monkeypatch) -> None:
    _patch_gurobi(monkeypatch, _RaisingSolver())
    with pytest.warns(MilpSolverFallbackWarning, match="falling back to highs") as record:
        result = solve_operational_milp(tiny7_ctx.bundle, solver="auto", context=tiny7_ctx)
    assert record[0].filename == __file__
    assert result["solver"] == "highs"
    assert result["outcome"] == "optimal"
    assert result["objective"] == pytest.approx(TINY7_OBJECTIVE, abs=1e-6)
    assert result["warnings"][0].startswith("gurobi failed (FakeGurobiError: Model too large")


def test_auto_without_gurobi_uses_highs_silently(tiny7_ctx, monkeypatch) -> None:
    _patch_gurobi(monkeypatch, None)
    with warnings.catch_warnings():
        warnings.simplefilter("error", MilpSolverFallbackWarning)
        result = solve_operational_milp(tiny7_ctx.bundle, solver="AUTO", context=tiny7_ctx)
    assert result["solver"] == "highs"
    assert result["outcome"] == "optimal"
    assert result["warnings"] == []


def test_legacy_auto_driver_falls_back_after_a_gurobi_exception(tiny7_ctx, monkeypatch) -> None:
    _patch_gurobi(monkeypatch, _RaisingSolver())
    monkeypatch.setattr(hd, "_operational_solver_available", lambda name: True)
    with pytest.warns(LegacyMipDeprecationWarning):
        result = solve_mip(tiny7_ctx.problem, time_limit=60, driver="auto")
    assert result["solver"] == "highs"
    assert result["outcome"] == "optimal"
    assert result["warnings"][0].startswith("gurobi failed (FakeGurobiError")
    with pytest.warns(LegacyMipDeprecationWarning):
        explicit = solve_mip(tiny7_ctx.problem, time_limit=60, driver="gurobi")
    assert explicit["outcome"] == "error"
    assert explicit["solver_error"].startswith("FakeGurobiError")


def test_legacy_appsi_runner_reports_exceptions(tiny7_ctx) -> None:
    run = hd._run_appsi(_RaisingSolver(), build_operational_model(tiny7_ctx.bundle))
    assert run.error == "FakeGurobiError: Model too large for size-limited license"
    assert run.has_solution is False


def test_real_gurobipy_failure_falls_back(monkeypatch) -> None:
    pytest.importorskip("gurobipy")
    ctx = build_operational_problem(
        Problem.from_scenario(load_scenario("examples/small21/scenario.yaml"))
    )
    gurobi = solve_operational_milp(ctx.bundle, solver="gurobi", time_limit=5)
    if gurobi["outcome"] != "error":
        pytest.skip("Gurobi licence can solve small21; no failure to fall back from")
    with pytest.warns(MilpSolverFallbackWarning):
        result = solve_operational_milp(ctx.bundle, solver="auto", time_limit=5)
    assert result["solver"] == "highs"
    assert result["solver_error"] is None
