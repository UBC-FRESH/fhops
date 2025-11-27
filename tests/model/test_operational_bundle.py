from fhops.model.milp.data import OperationalMilpBundle, build_operational_bundle
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario


def test_build_operational_bundle_basic_sets() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)

    bundle = build_operational_bundle(problem)
    assert isinstance(bundle, OperationalMilpBundle)

    assert set(bundle.machines) == {machine.id for machine in scenario.machines}
    assert set(bundle.blocks) == {block.id for block in scenario.blocks}
    assert set(bundle.days) == set(problem.days)
    assert set(bundle.shifts) == {(shift.day, shift.shift_id) for shift in problem.shifts}

    # Ensure every block is associated with a harvest system and system metadata exists.
    for block_id, system_id in bundle.block_system.items():
        assert block_id in bundle.blocks
        assert system_id in bundle.systems
        system_config = bundle.systems[system_id]
        assert system_config.roles, "system must expose at least one role"

    # Production rate lookup should cover every (machine, block) pair present in scenario data.
    for rate in scenario.production_rates:
        key = (rate.machine_id, rate.block_id)
        assert key in bundle.production_rates
        assert bundle.production_rates[key] == rate.rate
