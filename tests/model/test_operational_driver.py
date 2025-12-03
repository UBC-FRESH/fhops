from types import SimpleNamespace

import pandas as pd

from fhops.model.milp.data import build_operational_bundle

from fhops.model.milp.driver import solve_operational_milp, _apply_incumbent_start
from fhops.model.milp.operational import build_operational_model
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario


def test_solve_operational_milp_runs_highs(tmp_path):
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)

    result = solve_operational_milp(bundle, solver="highs", time_limit=1)
    assert result["solver_status"] in {"ok", "warning", "aborted"}
    assert isinstance(result["assignments"], pd.DataFrame)
    assert "objective" in result


def test_apply_incumbent_start_sets_initial_values():
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)
    model = build_operational_model(bundle)

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


def test_solve_operational_milp_uses_warmstart(monkeypatch):
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)

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
    result = solve_operational_milp(bundle, solver="highs", incumbent_assignments=incumbent)
    assert result["solver_status"] == "warning"
    assert captured["kwargs"].get("warmstart") is True
