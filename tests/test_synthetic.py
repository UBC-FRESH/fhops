from fhops.scenario.contract import SalvageProcessingMode
from fhops.scenario.synthetic import (
    SyntheticScenarioSpec,
    generate_basic,
    generate_with_systems,
)
from fhops.scheduling.systems import default_system_registry


def test_generate_basic_produces_consistent_counts():
    spec = SyntheticScenarioSpec(num_blocks=3, num_days=4, num_machines=2)
    scenario = generate_basic(spec)

    assert len(scenario.blocks) == 3
    assert len(scenario.machines) == 2
    assert len(scenario.calendar) == 2 * 4
    assert scenario.num_days == 4
    assert scenario.timeline is None


def test_generate_basic_with_blackouts():
    spec = SyntheticScenarioSpec(
        num_blocks=1,
        num_days=5,
        num_machines=1,
        blackout_days=[3, 4],
    )
    scenario = generate_basic(spec)
    assert scenario.timeline is not None
    blackout_days = {bw.start_day for bw in scenario.timeline.blackouts}
    assert blackout_days == {3, 4}


def test_generate_with_systems_assigns_system_ids():
    spec = SyntheticScenarioSpec(num_blocks=4, num_days=4, num_machines=2)
    scenario = generate_with_systems(spec)
    system_ids = {block.harvest_system_id for block in scenario.blocks}
    assert None not in system_ids
    assert len(system_ids) >= 2
    machine_roles = {machine.role for machine in scenario.machines}
    assert None not in machine_roles


def test_generate_with_systems_assigns_salvage_processing_mode():
    spec = SyntheticScenarioSpec(num_blocks=3, num_days=3, num_machines=2)
    systems = default_system_registry()
    salvage_only = {
        system_id: systems[system_id]
        for system_id in ("ground_salvage_grapple", "cable_salvage_grapple")
    }
    scenario = generate_with_systems(spec, systems=salvage_only)
    salvage_blocks = [
        block
        for block in scenario.blocks
        if block.harvest_system_id in salvage_only and block.salvage_processing_mode is not None
    ]
    assert salvage_blocks, "Expected salvage blocks to be tagged with a processing mode."
    assert all(
        block.salvage_processing_mode == SalvageProcessingMode.STANDARD_MILL
        for block in salvage_blocks
    )


def test_generate_with_systems_attaches_road_construction_defaults():
    systems = default_system_registry()
    cable_only = {"cable_running": systems["cable_running"]}
    spec = SyntheticScenarioSpec(num_blocks=2, num_days=2, num_machines=2)
    scenario = generate_with_systems(spec, systems=cable_only)
    assert scenario.road_construction is not None
    assert len(scenario.road_construction) == 1
    entry = scenario.road_construction[0]
    assert entry.machine_slug == "caterpillar_235_hydraulic_backhoe"
    assert entry.road_length_m > 0
