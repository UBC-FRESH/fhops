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


def test_random_dataset_statistics_within_bounds():
    config = SyntheticDatasetConfig(
        name="synthetic-stats",
        num_blocks=(10, 10),
        num_days=(12, 12),
        num_machines=(4, 4),
        num_landings=(2, 2),
        availability_probability=0.7,
        production_rate=(5.0, 15.0),
        work_required=(5.0, 15.0),
        blackout_probability=0.2,
        blackout_duration=(1, 2),
    )

    availability_ratios: list[float] = []
    blackout_counts: list[int] = []
    for seed in range(10):
        bundle = generate_random_dataset(config, seed=seed)
        availability_ratios.append(float(bundle.calendar["available"].mean()))
        scenario = bundle.scenario
        if scenario.timeline is not None:
            blackout_counts.append(len(scenario.timeline.blackouts))

        # production/work bounds
        assert bundle.blocks["work_required"].between(5.0, 15.0).all()
        assert bundle.production_rates["rate"].between(5.0, 15.0).all()

    avg_availability = sum(availability_ratios) / len(availability_ratios)
    assert abs(avg_availability - config.availability_probability) <= 0.15

    if blackout_counts:
        avg_blackouts = sum(blackout_counts) / len(blackout_counts)
        if isinstance(config.num_days, tuple):
            num_days = config.num_days[1]
        else:
            num_days = config.num_days
        expected = config.blackout_probability * num_days
        assert avg_blackouts <= expected + 2
