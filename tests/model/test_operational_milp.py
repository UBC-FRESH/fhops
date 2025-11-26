import pyomo.environ as pyo

from fhops.model.milp.data import build_operational_bundle
from fhops.model.milp.operational import build_operational_model
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario


def test_operational_model_builds_for_minitoy() -> None:
    scenario = load_scenario("examples/minitoy/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)

    model = build_operational_model(bundle)
    assert isinstance(model, pyo.ConcreteModel)
    assert len(model.M) == len(bundle.machines)
    assert len(model.B) == len(bundle.blocks)
    assert len(model.block_balance) == len(bundle.blocks)


def test_operational_model_has_production_limits() -> None:
    scenario = load_scenario("examples/minitoy/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)
    model = build_operational_model(bundle)

    some_machine = next(iter(bundle.machines))
    some_block = next(iter(bundle.blocks))
    some_slot = next(iter(bundle.shifts))

    rate = bundle.production_rates.get((some_machine, some_block), 0.0)
    if rate == 0:
        rate = 1.0

    model.x[some_machine, some_block, some_slot].fix(1)
    model.prod[some_machine, some_block, some_slot].setub(rate)
    assert model.prod[some_machine, some_block, some_slot].ub == rate
