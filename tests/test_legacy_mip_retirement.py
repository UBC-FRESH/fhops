"""Retirement of the legacy MIP (#127): delegation to the operational MILP and ILS warm start.

``solve_mip`` / ``fhops solve-mip`` warn and delegate to the operational MILP with the #124 result
contract and exit codes; ``fhops benchmark`` uses the operational MILP without a deprecation; the
ILS hybrid step warm-starts the operational MILP from the best ILS schedule (#104).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pyomo.environ as pyo
import pytest

import fhops.model.milp.driver as milp_driver
import fhops.optimization.heuristics.ils as ils_module
import fhops.optimization.mip.highs_driver as hd
from fhops.cli.benchmarks import run_benchmark_suite
from fhops.cli.main import app
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.heuristics import solve_ils
from fhops.optimization.mip import LegacyMipDeprecationWarning, build_model, solve_mip
from fhops.optimization.mip.highs_driver import (
    ASSIGNMENT_COLUMNS,
    SolverUnavailable,
    operational_solver_for_driver,
    solve_with_operational_milp,
)
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from tests.cli import CliRunner, cli_text

TINY7 = "examples/tiny7/scenario.yaml"
REGRESSION = "tests/fixtures/regression/regression.yaml"
# Operational MILP optimum for tiny7 (HiGHS). 4388.082752 up to #125, when the capacity-1 landings
# became a hard per-shift-slot limit (landing_surplus weight 0), see §8.18.
TINY7_OPERATIONAL_OBJECTIVE = 279.796036


@pytest.fixture(scope="module")
def tiny7() -> Problem:
    return Problem.from_scenario(load_scenario(TINY7))


@pytest.fixture(scope="module")
def tiny7_operational(tiny7) -> dict:
    ctx = build_operational_problem(tiny7)
    return milp_driver.solve_operational_milp(ctx.bundle, time_limit=60, context=ctx)


def _fake_result(**overrides) -> dict:
    result = {
        "objective": None,
        "production": 0.0,
        "assignments": pd.DataFrame(columns=ASSIGNMENT_COLUMNS),
        "has_solution": False,
        "outcome": "no_solution",
        "solver_status": "unknown",
        "termination_condition": "unknown",
        "solver_error": None,
        "warnings": [],
        "warm_start": {},
    }
    result.update(overrides)
    return result


# --- Python API ---------------------------------------------------------------------------------


def test_deprecation_warning_category() -> None:
    assert issubclass(LegacyMipDeprecationWarning, DeprecationWarning)


def test_solve_mip_warns_and_returns_the_operational_result(tiny7, tiny7_operational) -> None:
    with pytest.warns(LegacyMipDeprecationWarning, match="solve-mip-operational"):
        result = solve_mip(tiny7, time_limit=60, driver="highs")
    assert result["has_solution"] is True
    assert result["outcome"] == "optimal"
    assert result["solver_error"] is None
    assert result["solver"] == "highs"
    assert result["objective"] == pytest.approx(TINY7_OPERATIONAL_OBJECTIVE, abs=1e-6)
    assert result["objective"] == pytest.approx(tiny7_operational["objective"], abs=1e-6)
    assert list(result["assignments"].columns) == ASSIGNMENT_COLUMNS
    assert not result["assignments"].empty
    for key in ("solver_status", "termination_condition", "warnings", "production", "warm_start"):
        assert key in result


def test_solve_with_operational_milp_does_not_warn(tiny7) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", LegacyMipDeprecationWarning)
        result = solve_with_operational_milp(tiny7, time_limit=60, driver="highs-exec")
    assert result["objective"] == pytest.approx(TINY7_OPERATIONAL_OBJECTIVE, abs=1e-6)


def test_build_model_warns(tiny7) -> None:
    with pytest.warns(LegacyMipDeprecationWarning, match="build_operational_model"):
        build_model(tiny7)


def test_driver_mapping() -> None:
    assert operational_solver_for_driver("auto") == ("gurobi", "highs")
    for driver in ("highs", "HIGHS-APPSI", "appsi", "highs-exec", "exec"):
        assert operational_solver_for_driver(driver) == ("highs",)
    assert operational_solver_for_driver("gurobi") == ("gurobi",)
    assert operational_solver_for_driver("gurobi-appsi") == ("appsi_gurobi",)
    assert operational_solver_for_driver("gurobi-direct") == ("gurobi_direct",)
    with pytest.raises(ValueError, match="Unknown MIP driver"):
        operational_solver_for_driver("cplex")


def test_auto_without_gurobi_uses_highs(tiny7, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_operational_solver_available", lambda name: name == "highs")
    result = solve_with_operational_milp(tiny7, driver="auto")
    assert result["solver"] == "highs"
    assert result["outcome"] == "optimal"
    assert result["warnings"] == []


def test_auto_falls_back_to_highs_after_a_gurobi_error(tiny7, monkeypatch) -> None:
    calls: list[str] = []

    def _fake(bundle, *, solver, **kwargs):
        calls.append(solver)
        if solver == "gurobi":
            return _fake_result(outcome="error", solver_error="license expired")
        return _fake_result(objective=1.0, has_solution=True, outcome="optimal")

    monkeypatch.setattr(hd, "_operational_solver_available", lambda name: True)
    monkeypatch.setattr(milp_driver, "solve_operational_milp", _fake)
    result = solve_with_operational_milp(tiny7, driver="auto")
    assert calls == ["gurobi", "highs"]
    assert result["solver"] == "highs"
    assert result["outcome"] == "optimal"
    assert result["warnings"][0].startswith("gurobi failed (license expired)")


def test_explicit_gurobi_error_is_returned(tiny7, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_operational_solver_available", lambda name: True)
    monkeypatch.setattr(
        milp_driver,
        "solve_operational_milp",
        lambda bundle, **kwargs: _fake_result(outcome="error", solver_error="license expired"),
    )
    result = solve_with_operational_milp(tiny7, driver="gurobi")
    assert result["outcome"] == "error"
    assert result["solver_error"] == "license expired"
    assert result["warnings"] == []


def test_missing_solver_raises_unavailable_and_unknown_driver_raises(tiny7, monkeypatch) -> None:
    monkeypatch.setattr(hd, "_operational_solver_available", lambda name: False)
    for driver in ("auto", "highs", "gurobi", "gurobi-appsi", "gurobi-direct"):
        with pytest.raises(SolverUnavailable):
            solve_with_operational_milp(tiny7, driver=driver)
    with pytest.warns(LegacyMipDeprecationWarning), pytest.raises(ValueError):
        solve_mip(tiny7, driver="cplex")


# --- CLI ----------------------------------------------------------------------------------------


def test_cli_solve_mip_delegates_to_the_operational_milp(tmp_path, tiny7_operational) -> None:
    out = tmp_path / "mip.csv"
    with pytest.warns(LegacyMipDeprecationWarning):
        result = CliRunner().invoke(
            app, ["solve-mip", TINY7, "--out", str(out), "--driver", "highs"]
        )
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert text.count("Deprecated:") == 1
    assert "solve-mip-operational" in text
    assert "MIP outcome=optimal" in text
    assert f"objective={TINY7_OPERATIONAL_OBJECTIVE:.3f}" in text
    assert "Total production" in text or "total_production" in text.lower()
    frame = pd.read_csv(out)
    assert list(frame.columns) == ASSIGNMENT_COLUMNS
    assert len(frame) == len(tiny7_operational["assignments"])


def _patch_cli_solve_mip(monkeypatch, result: dict) -> None:
    monkeypatch.setattr("fhops.cli.main.solve_mip", lambda pb, **kwargs: dict(result))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"outcome": "infeasible", "termination_condition": "infeasible"},
            "the model is infeasible",
        ),
        (
            {"outcome": "no_solution", "termination_condition": "maxTimeLimit"},
            "stopped without a feasible solution",
        ),
    ],
)
def test_cli_solve_mip_without_solution_exits_zero(monkeypatch, tmp_path, payload, expected):
    _patch_cli_solve_mip(monkeypatch, _fake_result(**payload))
    out = tmp_path / "m.csv"
    result = CliRunner().invoke(app, ["solve-mip", TINY7, "--out", str(out)])
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert f"outcome={payload['outcome']}" in text
    assert "objective=n/a" in text
    assert expected in text
    frame = pd.read_csv(out)
    assert frame.empty and list(frame.columns) == ASSIGNMENT_COLUMNS


def test_cli_solve_mip_empty_incumbent_skips_kpis(monkeypatch, tmp_path) -> None:
    _patch_cli_solve_mip(
        monkeypatch, _fake_result(objective=-8.0, has_solution=True, outcome="optimal")
    )
    result = CliRunner().invoke(app, ["solve-mip", TINY7, "--out", str(tmp_path / "m.csv")])
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "objective=-8.000" in text
    assert "assigns no machines" in text


def test_cli_solve_mip_solver_error_exits_one(monkeypatch, tmp_path) -> None:
    _patch_cli_solve_mip(
        monkeypatch,
        _fake_result(
            outcome="error",
            solver_error="ERROR:   Option 'threads' is set to 997",
            warnings=["gurobi failed (x); falling back to highs (driver=auto)."],
        ),
    )
    out = tmp_path / "m.csv"
    result = CliRunner().invoke(app, ["solve-mip", TINY7, "--out", str(out)])
    text = cli_text(result)
    assert result.exit_code == 1, text
    assert "outcome=error" in text
    assert "Solver error" in text
    assert "Warning:" in text
    assert "infeasible" not in text
    assert pd.read_csv(out).empty


@pytest.mark.filterwarnings(
    "ignore::fhops.optimization.mip.deprecation.LegacyMipDeprecationWarning"
)
def test_cli_solve_mip_unavailable_and_bad_driver(monkeypatch, tmp_path) -> None:
    out = str(tmp_path / "m.csv")
    result = CliRunner().invoke(app, ["solve-mip", TINY7, "--out", out, "--driver", "nope"])
    assert result.exit_code == 2, cli_text(result)

    monkeypatch.setattr(hd, "_operational_solver_available", lambda name: False)
    result = CliRunner().invoke(app, ["solve-mip", TINY7, "--out", out])
    text = cli_text(result)
    assert result.exit_code == 1, text
    assert "Solver unavailable" in text


def test_cli_benchmark_uses_the_operational_milp(tmp_path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", LegacyMipDeprecationWarning)
        result = CliRunner().invoke(
            app,
            ["benchmark", TINY7, "--out-dir", str(tmp_path), "--iters", "50", "--driver", "highs"],
        )
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "Deprecated" not in text
    assert f"MIP obj={TINY7_OPERATIONAL_OBJECTIVE:.3f}" in text
    assert "MIP metrics:" in text
    assert "SA metrics:" in text
    assert not pd.read_csv(tmp_path / "mip_solution.csv").empty
    assert not pd.read_csv(tmp_path / "sa_solution.csv").empty


def test_cli_benchmark_handles_missing_mip_solution(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        hd,
        "solve_with_operational_milp",
        lambda pb, **kwargs: _fake_result(outcome="infeasible"),
    )
    result = CliRunner().invoke(
        app, ["benchmark", TINY7, "--out-dir", str(tmp_path), "--iters", "50"]
    )
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "MIP obj=n/a (outcome=infeasible)" in text
    assert "MIP metrics skipped" in text
    assert "SA metrics:" in text
    assert pd.read_csv(tmp_path / "mip_solution.csv").empty


def test_cli_benchmark_solver_error_exits_one(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        hd,
        "solve_with_operational_milp",
        lambda pb, **kwargs: _fake_result(outcome="error", solver_error="solver exploded"),
    )
    result = CliRunner().invoke(
        app, ["benchmark", TINY7, "--out-dir", str(tmp_path), "--iters", "20"]
    )
    text = cli_text(result)
    assert result.exit_code == 1, text
    assert "MIP solver error" in text
    assert "SA metrics:" in text


def test_bench_suite_auto_falls_back_to_highs(tmp_path, monkeypatch) -> None:
    # Gurobi is not installed here: since #115 the driver reports this as solver_error instead of
    # raising, which used to leave the MIP row empty for driver=auto.
    real = milp_driver.solve_operational_milp
    tried: list[str] = []

    def _spy(bundle, solver="highs", **kwargs):
        tried.append(solver)
        if solver == "gurobi":
            return _fake_result(outcome="error", solver_error="No executable found")
        return real(bundle, solver=solver, **kwargs)

    monkeypatch.setattr("fhops.cli.benchmarks.solve_operational_milp", _spy)
    summary = run_benchmark_suite(
        [Path(TINY7)],
        tmp_path,
        time_limit=60,
        driver="auto",
        include_mip=True,
        include_sa=False,
    )
    assert tried == ["gurobi", "highs"]
    row = summary[summary["solver"] == "mip"].iloc[0]
    assert row["objective"] == pytest.approx(TINY7_OPERATIONAL_OBJECTIVE, abs=1e-6)


# --- ILS hybrid warm start ----------------------------------------------------------------------


def test_ils_hybrid_warm_starts_the_operational_milp(tiny7, monkeypatch) -> None:
    real = milp_driver.solve_operational_milp
    calls: list[dict] = []

    def _spy(bundle, **kwargs):
        result = real(bundle, **kwargs)
        calls.append({"bundle": bundle, "kwargs": kwargs, "result": result})
        return result

    monkeypatch.setattr(ils_module, "solve_operational_milp", _spy)
    result = solve_ils(
        tiny7, iters=3, seed=1, stall_limit=1, hybrid_use_mip=True, hybrid_mip_time_limit=60
    )
    assert calls, "hybrid step did not run"
    records = result["meta"]["hybrid_mip"]
    assert len(records) == len(calls)
    first = calls[0]
    incumbent = first["kwargs"]["incumbent_assignments"]
    assert incumbent is not None and not incumbent.empty
    warm = first["result"]["warm_start"]
    assert warm["method"] == "appsi_highs"
    assert warm["seeded_slots"] == len(incumbent)
    assert warm["accepted"] is True
    assert records[0]["warm_start_accepted"] is True
    assert records[0]["outcome"] == "optimal"

    # Objective of the seeded ILS schedule in the MILP's own terms.
    model = build_operational_model(first["bundle"])
    model._warm_start_meta["operational_problem"] = first["kwargs"]["context"]
    assert milp_driver._apply_incumbent_start(model, incumbent) == len(incumbent)
    seed_objective = float(pyo.value(model.objective))
    assert first["result"]["objective"] >= seed_objective - 1e-6
    assert result["objective"] >= records[0]["seed_score"]


def test_ils_hybrid_without_solution_keeps_the_ils_schedule(tiny7, monkeypatch) -> None:
    baseline = solve_ils(tiny7, iters=4, seed=5, stall_limit=1)
    monkeypatch.setattr(
        ils_module,
        "solve_operational_milp",
        lambda bundle, **kwargs: _fake_result(
            outcome="infeasible", termination_condition="infeasible"
        ),
    )
    hybrid = solve_ils(tiny7, iters=4, seed=5, stall_limit=1, hybrid_use_mip=True)
    assert hybrid["objective"] == baseline["objective"]
    pd.testing.assert_frame_equal(
        hybrid["assignments"].reset_index(drop=True), baseline["assignments"].reset_index(drop=True)
    )
    records = hybrid["meta"]["hybrid_mip"]
    assert records and all(r["outcome"] == "infeasible" and not r["adopted"] for r in records)
    assert all(r["hybrid_score"] is None for r in records)


def test_cli_build_mip_builds_the_operational_milp_with_a_notice() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", LegacyMipDeprecationWarning)
        result = CliRunner().invoke(app, ["build-mip", TINY7])
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert text.count("Deprecated:") == 1
    assert "builds the operational MILP" in text
    model = build_operational_model(
        build_operational_problem(Problem.from_scenario(load_scenario(TINY7))).bundle
    )
    constraints = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))
    assert "Operational MILP built with |M|=9 |B|=2 |S|=7 slots" in text
    assert f"constraints={constraints}" in text


def test_cli_build_mip_reports_a_missing_scenario(tmp_path) -> None:
    result = CliRunner().invoke(app, ["build-mip", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 1
    assert "Build failed" in cli_text(result)
