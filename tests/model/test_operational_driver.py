import pandas as pd

from fhops.model.milp.data import build_operational_bundle
from fhops.model.milp.driver import solve_operational_milp
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario


def test_solve_operational_milp_runs_highs(tmp_path):
    scenario = load_scenario("examples/minitoy/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)

    result = solve_operational_milp(bundle, solver="highs", time_limit=1)
    assert result["solver_status"] in {"ok", "warning", "aborted"}
    assert isinstance(result["assignments"], pd.DataFrame)
    assert "objective" in result
