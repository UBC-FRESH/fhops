from types import SimpleNamespace

import pandas as pd
import pytest

from fhops.model.milp.driver import _apply_incumbent_start, solve_operational_milp
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

    transition_var = model.y["H1", "B01", "B02", (2, "S1")]
    assert transition_var.value == 1.0

    leftover_b01 = model.leftover["B01"].value
    system_id = bundle.block_system["B01"]
    terminal_roles = ctx.terminal_roles.get(system_id, frozenset())
    delivered = 0.0
    for role in terminal_roles:
        for shift in model.S:
            delivered += model.role_prod[role, "B01", shift].value
    expected_leftover = max(0.0, bundle.work_required["B01"] - delivered)
    assert leftover_b01 == pytest.approx(expected_leftover)


def test_solve_operational_milp_uses_warmstart(monkeypatch):
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    ctx = build_operational_problem(problem)
    bundle = ctx.bundle

    incumbent = pd.DataFrame(
        [
            {"machine_id": "H1", "block_id": "B01", "day": 1, "shift_id": "S1", "assigned": 1},
        ]
    )

    captured: dict[str, object] = {}

    class FakeSolver:
        def __init__(self):
            self.options: dict[str, object] = {}

        def solve(self, model, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                solver=SimpleNamespace(status="warning", termination_condition="maxTimeLimit")
            )

    def fake_factory(_solver_name: str):
        return FakeSolver()

    monkeypatch.setattr("fhops.model.milp.driver.SolverFactory", fake_factory)
    result = solve_operational_milp(
        bundle,
        solver="highs",
        incumbent_assignments=incumbent,
        context=ctx,
    )
    assert result["solver_status"] == "warning"
    assert captured["kwargs"].get("warmstart") is True
