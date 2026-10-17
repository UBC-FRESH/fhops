import warnings
from types import SimpleNamespace

import pandas as pd
import pytest

from fhops.model.milp.driver import (
    MilpWarmStartWarning,
    _accepts_warmstart_keyword,
    _apply_incumbent_start,
    solve_operational_milp,
)
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario


def test_solve_operational_milp_runs_highs(tmp_path):
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    ctx = build_operational_problem(problem)

    result = solve_operational_milp(ctx.bundle, solver="highs", time_limit=1, context=ctx)
    assert result["solver_status"] in {"ok", "warning", "aborted"}
    assert isinstance(result["assignments"], pd.DataFrame)
    assert "objective" in result


def test_apply_incumbent_start_sets_initial_values():
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    ctx = build_operational_problem(problem)
    bundle = ctx.bundle
    model = build_operational_model(bundle)
    getattr(model, "_warm_start_meta")["operational_problem"] = ctx

    machines = sorted(bundle.machines)
    blocks = sorted(bundle.blocks)
    shift = sorted(bundle.shifts)[0]
    mach = machines[0]
    blk = blocks[0]
    day, shift_id = shift

    df = pd.DataFrame(
        [
            {
                "machine_id": mach,
                "block_id": blk,
                "day": int(day),
                "shift_id": shift_id,
                "assigned": 1,
                "production": 5.5,
            }
        ]
    )

    seeded = _apply_incumbent_start(model, df)
    assert seeded == 1
    assert model.x[mach, blk, (day, shift_id)].value == 1
    assert model.prod[mach, blk, (day, shift_id)].value == 5.5


def test_apply_incumbent_start_populates_auxiliary_state():
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    ctx = build_operational_problem(problem)
    bundle = ctx.bundle
    model = build_operational_model(bundle)
    getattr(model, "_warm_start_meta")["operational_problem"] = ctx

    df = pd.DataFrame(
        [
            {
                "machine_id": "H1",
                "block_id": "B01",
                "day": 1,
                "shift_id": "S1",
                "assigned": 1,
                "production": 400.0,
            },
            {
                "machine_id": "H1",
                "block_id": "B02",
                "day": 2,
                "shift_id": "S1",
                "assigned": 1,
                "production": 300.0,
            },
            {
                "machine_id": "H3",
                "block_id": "B01",
                "day": 3,
                "shift_id": "S1",
                "assigned": 1,
                "production": 350.0,
            },
            {
                "machine_id": "H7",
                "block_id": "B01",
                "day": 4,
                "shift_id": "S1",
                "assigned": 1,
                "production": 250.0,
            },
        ]
    )

    seeded = _apply_incumbent_start(model, df)
    assert seeded == 4

    role_key = ("feller_buncher", "B01", (1, "S1"))
    assert model.role_prod[role_key].value == pytest.approx(400.0)

    # H1 moves B01 -> B02 on day 2 (tiny7 move costs are uniform per machine: hub arcs).
    assert model.depart["H1", "B01", 2, "S1"].value == 1.0
    assert model.arrive["H1", "B02", 2, "S1"].value == 1.0
    assert model.first["H1", "B01", 1, "S1"].value == 1.0
    assert model.stay["H1", "B02", 3, "S1"].value == 1.0
    assert model.unplaced["H1", 1, "S1"].value == 0.0
    assert model.unplaced["H3", 2, "S1"].value == 1.0

    leftover_b01 = model.leftover["B01"].value
    system_id = bundle.block_system["B01"]
    terminal_roles = ctx.terminal_roles.get(system_id, frozenset())
    delivered = 0.0
    for role in terminal_roles:
        for shift in model.S:
            delivered += model.role_prod[role, "B01", shift].value
    expected_leftover = max(0.0, bundle.work_required["B01"] - delivered)
    assert leftover_b01 == pytest.approx(expected_leftover)


def _tiny7_context():
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    return build_operational_problem(problem)


class _RecordingSolver:
    """Fake legacy Pyomo plugin that records ``solve`` keyword arguments."""

    def __init__(self, captured: dict[str, object], warm_start_capable: bool):
        self.options: dict[str, object] = {}
        self._captured = captured
        self._capable = warm_start_capable

    def warm_start_capable(self) -> bool:
        return self._capable

    def available(self, exception_flag: bool = True) -> bool:
        return True

    def solve(self, model, **kwargs):
        self._captured["kwargs"] = kwargs
        return SimpleNamespace(
            solver=SimpleNamespace(status="warning", termination_condition="other")
        )


def test_solve_operational_milp_forwards_warmstart_to_capable_plugins(monkeypatch):
    ctx = _tiny7_context()
    incumbent = pd.DataFrame(
        [
            {"machine_id": "H1", "block_id": "B01", "day": 1, "shift_id": "S1", "assigned": 1},
        ]
    )
    captured: dict[str, object] = {}
    requested: list[str] = []

    def fake_factory(solver_name: str):
        requested.append(solver_name)
        return _RecordingSolver(captured, warm_start_capable=True)

    monkeypatch.setattr("fhops.model.milp.driver.SolverFactory", fake_factory)
    with warnings.catch_warnings():
        warnings.simplefilter("error", MilpWarmStartWarning)
        result = solve_operational_milp(
            ctx.bundle,
            solver="gurobi",
            incumbent_assignments=incumbent,
            context=ctx,
        )
    assert requested == ["gurobi"]
    assert result["solver_status"] == "warning"
    assert captured["kwargs"].get("warmstart") is True
    assert result["warm_start"]["method"] == "pyomo_warmstart"
    assert result["warm_start"]["seeded_slots"] == 1


def test_solve_operational_milp_warns_when_solver_lacks_warmstart(monkeypatch):
    ctx = _tiny7_context()
    incumbent = pd.DataFrame(
        [
            {"machine_id": "H1", "block_id": "B01", "day": 1, "shift_id": "S1", "assigned": 1},
        ]
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "fhops.model.milp.driver.SolverFactory",
        lambda _name: _RecordingSolver(captured, warm_start_capable=False),
    )
    with pytest.warns(MilpWarmStartWarning, match="does not support MIP warm starts"):
        result = solve_operational_milp(
            ctx.bundle,
            solver="glpk",
            incumbent_assignments=incumbent,
            context=ctx,
        )
    assert "warmstart" not in captured["kwargs"]
    assert result["warm_start"]["method"] is None
    assert result["warm_start"]["requested"] is True
    assert result["objective"] is None


def test_contrib_highs_wrapper_does_not_take_warmstart_keyword():
    import pyomo.environ  # noqa: F401  (registers solver plugins)
    from pyomo.opt import SolverFactory

    assert _accepts_warmstart_keyword(SolverFactory("highs")) is False


@pytest.fixture(scope="module")
def tiny7_highs_solution():
    ctx = _tiny7_context()
    cold = solve_operational_milp(ctx.bundle, solver="highs", time_limit=60, context=ctx)
    assert cold["termination_condition"] == "optimal"
    assert cold["warm_start"]["method"] is None
    return ctx, cold


def test_highs_warm_start_is_accepted(tiny7_highs_solution, recwarn):
    ctx, cold = tiny7_highs_solution
    incumbent = cold["assignments"]

    warm = solve_operational_milp(
        ctx.bundle,
        solver="highs",
        time_limit=5,
        incumbent_assignments=incumbent,
        context=ctx,
    )

    assert not [w for w in recwarn if issubclass(w.category, MilpWarmStartWarning)]
    info = warm["warm_start"]
    assert info["method"] == "appsi_highs"
    assert info["solver"] == "appsi_highs"
    assert info["seeded_slots"] == len(incumbent)
    assert info["accepted"] is True
    assert any("MIP start solution is feasible" in msg for msg in info["solver_messages"])
    # The operational MILP maximises, so the warm-started solve must be at least as good.
    assert warm["objective"] is not None
    assert warm["objective"] >= cold["objective"] - 1e-6
    assert not warm["assignments"].empty


def test_highs_warm_start_survives_time_limit(tiny7_highs_solution):
    ctx, cold = tiny7_highs_solution

    warm = solve_operational_milp(
        ctx.bundle,
        solver="highs",
        time_limit=1e-6,
        incumbent_assignments=cold["assignments"],
        context=ctx,
    )

    # Even when HiGHS stops immediately it returns the supplied MIP start as its incumbent.
    assert warm["warm_start"]["method"] == "appsi_highs"
    assert warm["objective"] == pytest.approx(cold["objective"], abs=1e-6)
    assert not warm["assignments"].empty


def test_highs_warm_start_flags_infeasible_incumbent(tiny7_highs_solution):
    ctx, cold = tiny7_highs_solution
    incumbent = cold["assignments"].copy()
    incumbent["block_id"] = incumbent["block_id"].iloc[::-1].to_numpy()

    warm = solve_operational_milp(
        ctx.bundle,
        solver="highs",
        time_limit=5,
        incumbent_assignments=incumbent,
        context=ctx,
    )

    assert warm["warm_start"]["method"] == "appsi_highs"
    assert warm["warm_start"]["accepted"] is False
    assert warm["objective"] is not None


def test_highs_warm_start_falls_back_without_appsi(tiny7_highs_solution, monkeypatch):
    ctx, cold = tiny7_highs_solution
    monkeypatch.setattr("fhops.model.milp.driver._solver_available", lambda _opt: False)

    with pytest.warns(MilpWarmStartWarning, match="appsi_highs"):
        result = solve_operational_milp(
            ctx.bundle,
            solver="highs",
            time_limit=60,
            incumbent_assignments=cold["assignments"],
            context=ctx,
        )

    assert result["warm_start"]["method"] is None
    assert result["warm_start"]["solver"] == "highs"
    assert result["objective"] == pytest.approx(cold["objective"], abs=1e-6)
