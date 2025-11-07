from fhops.scenario.synthetic import SyntheticScenarioSpec, generate_basic


def test_generate_basic_produces_consistent_counts():
    spec = SyntheticScenarioSpec(num_blocks=3, num_days=4, num_machines=2)
    scenario = generate_basic(spec)

    assert len(scenario.blocks) == 3
    assert len(scenario.machines) == 2
    assert len(scenario.calendar) == 2 * 4
    assert scenario.num_days == 4
