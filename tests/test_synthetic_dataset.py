from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

from fhops.scenario.contract import SalvageProcessingMode
from fhops.scenario.io import load_scenario
from fhops.scenario.synthetic import (
    BlackoutBias,
    SyntheticDatasetConfig,
    generate_random_dataset,
    sampling_config_for,
)
from fhops.scheduling.systems import default_system_registry


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
    assert "terrain" in bundle.blocks.columns
    assert "prescription" in bundle.blocks.columns
    assert "crew" in bundle.machines.columns
    assert bundle.metadata is not None
    assert bundle.metadata["crew_capabilities"]

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

    metadata_path = out_dir / "metadata.yaml"
    assert metadata_path.exists()
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    assert metadata["crew_capabilities"]
    assert metadata["terrain_counts"]
    assert metadata["sampling_config"]["samples"] >= 1

    loaded = load_scenario(scenario_yaml)
    assert len(loaded.blocks) == len(bundle.blocks)
    assert len(loaded.machines) == len(bundle.machines)
    assert len(loaded.landings) == len(bundle.landings)
    assert len(loaded.calendar) == len(bundle.calendar)
    assert len(loaded.production_rates) == len(bundle.production_rates)

    # ensure timeline preserved
    assert loaded.timeline is not None
    assert loaded.crew_assignments is not None
    assert any(assignment.notes for assignment in loaded.crew_assignments or [])


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
        tier="large",
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
    blackout_durations: list[int] = []
    for seed in range(10):
        bundle = generate_random_dataset(config, seed=seed)
        availability_ratios.append(float(bundle.calendar["available"].mean()))
        scenario = bundle.scenario
        if scenario.timeline is not None:
            blackout_counts.append(len(scenario.timeline.blackouts))
            blackout_durations.extend(
                blackout.end_day - blackout.start_day + 1
                for blackout in scenario.timeline.blackouts
            )

        # production/work bounds
        assert bundle.blocks["work_required"].between(5.0, 15.0).all()
        assert bundle.production_rates["rate"].between(5.0, 15.0).all()
        assert "terrain" in bundle.blocks.columns
        assert bundle.metadata is not None
        assert bundle.metadata["tier"] == "large"

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
    assert any(length >= 2 for length in blackout_durations)


def test_salvage_blocks_round_trip_through_bundle(tmp_path: Path):
    config = SyntheticDatasetConfig(
        name="synthetic-salvage",
        num_blocks=(3, 3),
        num_days=(4, 4),
        num_machines=(2, 2),
        num_landings=(1, 1),
        blackout_probability=0.0,
        system_mix={"ground_salvage_grapple": 1.0},
    )
    systems = default_system_registry()
    salvage_system = {"ground_salvage_grapple": systems["ground_salvage_grapple"]}
    bundle = generate_random_dataset(config, seed=99, systems=salvage_system)

    assert set(bundle.blocks["harvest_system_id"]) == {"ground_salvage_grapple"}
    assert set(bundle.blocks["salvage_processing_mode"].dropna().unique()) == {
        SalvageProcessingMode.STANDARD_MILL.value
    }
    assert all(
        block.salvage_processing_mode == SalvageProcessingMode.STANDARD_MILL
        for block in bundle.scenario.blocks
    )

    scenario_yaml = bundle.write(tmp_path / "synthetic_salvage")
    loaded = load_scenario(scenario_yaml)
    assert all(
        block.salvage_processing_mode == SalvageProcessingMode.STANDARD_MILL
        for block in loaded.blocks
    )


def test_tier_defaults_drive_blackouts_and_crews():
    config = SyntheticDatasetConfig(
        name="synthetic-large-tier",
        tier="large",
        num_blocks=(16, 16),
        num_days=(18, 18),
        num_machines=(6, 6),
        num_landings=(3, 3),
        shifts_per_day=2,
    )

    blackout_totals = []
    crews_seen: set[str] = set()
    for seed in range(5):
        bundle = generate_random_dataset(config, seed=303 + seed)
        timeline = bundle.scenario.timeline
        assert timeline is not None
        blackout_totals.append(len(timeline.blackouts))
        for assignment in bundle.scenario.crew_assignments or []:
            crews_seen.add(assignment.crew_id)
    assert sum(blackout_totals) > 0
    assert crews_seen


def test_weighted_terrain_profile_skews_distribution():
    config = SyntheticDatasetConfig(
        name="weighted-terrain",
        tier=None,
        num_blocks=(12, 12),
        num_days=(8, 8),
        num_machines=(3, 3),
        terrain_pool=["gentle", "steep"],
        terrain_weights=[0.1, 0.9],
        blackout_probability=0.0,
    )
    counts: Counter[str] = Counter()
    for seed in range(10):
        bundle = generate_random_dataset(config, seed=seed)
        counts.update(bundle.blocks["terrain"])

    total = sum(counts.values())
    assert counts["steep"] / total > 0.65


def test_blackout_biases_increase_activity():
    bias = BlackoutBias(start_day=3, end_day=4, probability=0.9, duration=1)
    config = SyntheticDatasetConfig(
        name="biased-blackouts",
        tier=None,
        num_blocks=6,
        num_days=6,
        num_machines=3,
        blackout_probability=0.0,
        blackout_biases=[bias],
    )
    observed: list[list[tuple[int, int]]] = []
    for seed in range(5):
        bundle = generate_random_dataset(config, seed=seed)
        blackouts = [
            (b.start_day, b.end_day)
            for b in bundle.scenario.timeline.blackouts  # type: ignore[union-attr]
        ]
        observed.append(blackouts)

    assert any(any(3 <= start <= 4 for start, _ in blackouts) for blackouts in observed)


def test_system_mix_applies_when_systems_provided():
    systems = dict(default_system_registry())
    selected_systems = {key: systems[key] for key in list(systems.keys())[:2]}
    mix = {list(selected_systems.keys())[0]: 0.8, list(selected_systems.keys())[1]: 0.2}
    config = SyntheticDatasetConfig(
        name="system-mix",
        tier=None,
        num_blocks=20,
        num_days=6,
        num_machines=4,
        system_mix=mix,
    )

    bundle = generate_random_dataset(config, seed=99, systems=selected_systems)
    assignments = Counter(
        block.harvest_system_id for block in bundle.scenario.blocks if block.harvest_system_id
    )
    total = sum(assignments.values())
    dominant = max(assignments.values()) / total
    assert dominant > 0.6


def test_sampling_config_for_tier_defaults():
    config = SyntheticDatasetConfig(
        name="tier-medium",
        tier="medium",
        num_blocks=(8, 8),
        num_days=(10, 10),
        num_machines=(4, 4),
    )
    sampling = sampling_config_for(config)
    assert sampling.samples == 12
    assert sampling.downtime.enabled is True
    assert pytest.approx(0.12, rel=1e-6) == sampling.downtime.probability  # type: ignore[name-defined]
    assert sampling.weather.enabled is True
    assert sampling.weather.day_probability > 0.2
    assert sampling.landing.enabled is True


def test_sampling_config_override_merges(tmp_path: Path):
    config = SyntheticDatasetConfig(
        name="override",
        tier="small",
        num_blocks=6,
        num_days=6,
        num_machines=3,
        sampling_overrides={
            "samples": 20,
            "downtime": {"enabled": True, "probability": 0.5},
        },
    )
    sampling = sampling_config_for(config)
    assert sampling.samples == 20
    assert sampling.downtime.enabled is True
    assert sampling.downtime.probability == 0.5
