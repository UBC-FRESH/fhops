from __future__ import annotations

from pathlib import Path

from fhops.scenario.io import load_scenario
from fhops.scenario.synthetic import (
    SyntheticDatasetConfig,
    generate_random_dataset,
)


def test_generate_random_dataset_bundle(tmp_path: Path):
    config = SyntheticDatasetConfig(
        name="synthetic-med",
        num_blocks=(6, 6),
        num_days=(10, 10),
        num_machines=(3, 3),
        num_landings=(2, 2),
        role_pool=["logger", "forwarder"],
        blackout_probability=0.0,
    )

    bundle = generate_random_dataset(config, seed=7)

    assert len(bundle.blocks) == 6
    assert len(bundle.machines) == 3
    assert sorted(bundle.machines["role"].dropna().unique()) == ["forwarder", "logger"]

    out_dir = tmp_path / "synthetic_med"
    scenario_yaml = bundle.write(out_dir)

    for filename in [
        "data/blocks.csv",
        "data/machines.csv",
        "data/landings.csv",
        "data/calendar.csv",
        "data/prod_rates.csv",
    ]:
        assert (out_dir / filename).exists()

    loaded = load_scenario(scenario_yaml)
    assert len(loaded.blocks) == len(bundle.blocks)
    assert len(loaded.machines) == len(bundle.machines)
    assert len(loaded.landings) == len(bundle.landings)
    assert len(loaded.calendar) == len(bundle.calendar)
    assert len(loaded.production_rates) == len(bundle.production_rates)

    # ensure timeline preserved
    assert loaded.timeline is not None


def test_reference_dataset_loads():
    scenario_path = Path("examples/synthetic/small/scenario.yaml")
    scenario = load_scenario(scenario_path)

    assert scenario.name == "synthetic-small"
    assert scenario.blocks
    assert scenario.machines
    assert scenario.timeline is not None
