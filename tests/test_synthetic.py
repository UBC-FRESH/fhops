from fhops.scenario.synthetic import (
    SyntheticScenarioSpec,
    generate_basic,
    generate_with_systems,
)


def test_generate_basic_produces_consistent_counts():
    spec = SyntheticScenarioSpec(num_blocks=3, num_days=4, num_machines=2)
    scenario = generate_basic(spec)

    assert len(scenario.blocks) == 3
    assert len(scenario.machines) == 2
    assert len(scenario.calendar) == 2 * 4
    assert scenario.num_days == 4


def test_generate_with_systems_assigns_system_ids():
    spec = SyntheticScenarioSpec(num_blocks=4, num_days=4, num_machines=2)
    scenario = generate_with_systems(spec)
    system_ids = {block.harvest_system_id for block in scenario.blocks}
    assert None not in system_ids
    assert len(system_ids) >= 2
    machine_roles = {machine.role for machine in scenario.machines}
    assert None not in machine_roles
