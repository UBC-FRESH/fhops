#!/usr/bin/env python3
"""Regenerate canonical FHOPS reference datasets (tiny7, small21, med42, large84)."""

from __future__ import annotations

import argparse
import csv
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path
from textwrap import dedent

import yaml

from fhops.productivity import (
    ADV6N7DeckingMode,
    LahrsenModel,
    estimate_grapple_skidder_productivity_adv6n7,
    estimate_loader_forwarder_productivity_tn261,
    estimate_processor_productivity_berry2019,
    estimate_productivity,
)

DAILY_HOURS = 24.0
DEFAULT_LANDINGS = ("L1", "L2", "L3", "L4")
OBJECTIVE_WEIGHTS = {"production": 1.0, "mobilisation": 0.5}


@dataclass(frozen=True)
class BlockProfile:
    """Sampling parameters for a block category."""

    weight: float
    area_range: tuple[float, float]
    avg_stem_range: tuple[float, float]
    volume_per_ha_range: tuple[float, float]
    slope_range: tuple[float, float]
    window_span: tuple[int, int]


@dataclass
class BlockRecord:
    """Minimal block metadata required for CSV exports."""

    id: str
    landing_id: str
    harvest_system_id: str | None
    work_required: float
    earliest_start: int
    latest_finish: int
    avg_stem_size_m3: float
    volume_per_ha_m3: float
    stem_density_per_ha: float
    ground_slope_percent: float
    volume_per_ha_m3_sigma: float
    stem_density_per_ha_sigma: float

    def to_row(self) -> dict[str, float | int | str]:
        return self.__dict__


@dataclass(frozen=True)
class DatasetConfig:
    """Configuration for a synthetic reference dataset."""

    name: str
    label: str
    num_days: int
    num_blocks: int
    machines_by_role: dict[str, list[str]]
    block_profiles: tuple[BlockProfile, ...]
    landing_capacities: dict[str, int] = field(
        default_factory=lambda: {"L1": 2, "L2": 3, "L3": 2, "L4": 3}
    )
    landing_ids: tuple[str, ...] = DEFAULT_LANDINGS
    start_date: str = "2025-01-01"
    harvest_system_id: str = "ground_fb_skid"
    system_jobs: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("felling", "feller_buncher", ()),
        ("primary_transport", "grapple_skidder", ("felling",)),
        ("processing", "roadside_processor", ("primary_transport",)),
        ("loading", "loader", ("processing",)),
    )
    role_headstart_shifts: dict[str, float] = field(
        default_factory=lambda: {"roadside_processor": 0.0, "loader": 0.0}
    )
    loader_batch_volume_m3: float = 30.0
    work_scale: float = 1.0

    def machine_sequence(self) -> list[str]:
        ordered_roles = ("feller_buncher", "grapple_skidder", "roadside_processor", "loader")
        sequence: list[str] = []
        for role in ordered_roles:
            sequence.extend(self.machines_by_role.get(role, []))
        # append any remaining roles in deterministic order
        for role in sorted(self.machines_by_role):
            if role in ordered_roles:
                continue
            sequence.extend(self.machines_by_role[role])
        return sequence


def _sigma(value: float) -> float:
    return round(value * 0.2, 6)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _estimate_area_from_block(block: BlockRecord) -> float:
    if block.volume_per_ha_m3 <= 0:
        return 0.0
    return block.work_required / block.volume_per_ha_m3


def _estimate_skidding_distance(area_ha: float, landing_idx: int) -> tuple[float, float]:
    width_m = sqrt(max(area_ha, 0.01) * 10_000.0)
    mean_skid = width_m / 2.0
    distance = _clamp(mean_skid + landing_idx * 30.0 + 40.0, 120.0, 900.0)
    loader_distance = _clamp(distance * 0.55, 80.0, 360.0)
    return distance, loader_distance


def _sample_block(
    rng: random.Random,
    *,
    block_index: int,
    num_days: int,
    landing_ids: Sequence[str],
    profiles: tuple[BlockProfile, ...],
    harvest_system_id: str | None,
    work_scale: float,
) -> tuple[BlockRecord, float, float]:
    profile = rng.choices(profiles, weights=[p.weight for p in profiles], k=1)[0]
    area = rng.uniform(*profile.area_range)
    avg_stem = rng.uniform(*profile.avg_stem_range)
    volume_per_ha = rng.uniform(*profile.volume_per_ha_range)
    slope = rng.uniform(*profile.slope_range)
    stem_density = volume_per_ha / avg_stem
    work_required = round(area * volume_per_ha * work_scale, 6)
    # All reference datasets keep blocks available for the full horizon so the
    # scheduling problem focuses on sequencing and mobilisation rather than
    # blackout windows.
    earliest = 1
    latest = num_days
    landing = landing_ids[block_index % len(landing_ids)]

    record = BlockRecord(
        id=f"B{block_index + 1:02d}",
        landing_id=landing,
        harvest_system_id=harvest_system_id,
        work_required=work_required,
        earliest_start=earliest,
        latest_finish=latest,
        avg_stem_size_m3=round(avg_stem, 6),
        volume_per_ha_m3=round(volume_per_ha, 6),
        stem_density_per_ha=round(stem_density, 6),
        ground_slope_percent=round(slope, 2),
        volume_per_ha_m3_sigma=_sigma(volume_per_ha),
        stem_density_per_ha_sigma=_sigma(stem_density),
    )
    return record, area, slope


def _role_rates_for_block(
    *,
    block: BlockRecord,
    area: float,
    slope: float,
    landing_ids: Sequence[str],
) -> dict[str, float]:
    landing_idx = landing_ids.index(block.landing_id)
    distance, loader_distance = _estimate_skidding_distance(area, landing_idx)

    fb = estimate_productivity(
        avg_stem_size=block.avg_stem_size_m3,
        volume_per_ha=block.volume_per_ha_m3,
        stem_density=block.stem_density_per_ha,
        ground_slope=slope,
        model=LahrsenModel.DAILY,
        validate_ranges=False,
    )
    skidder = estimate_grapple_skidder_productivity_adv6n7(
        skidding_distance_m=distance,
        decking_mode=ADV6N7DeckingMode.SKIDDER_LOADER,
        utilisation=0.85,
        support_ratio=0.0,
    )
    processor = estimate_processor_productivity_berry2019(
        piece_size_m3=block.avg_stem_size_m3,
        tree_form_category=0,
        delay_multiplier=0.91,
    )
    loader = estimate_loader_forwarder_productivity_tn261(
        piece_size_m3=block.avg_stem_size_m3,
        external_distance_m=loader_distance,
        slope_percent=slope,
        bunched=True,
        delay_multiplier=0.9,
    )
    return {
        "feller_buncher": fb.predicted_m3_per_pmh * DAILY_HOURS,
        "grapple_skidder": skidder.productivity_m3_per_pmh * DAILY_HOURS,
        "roadside_processor": processor.productivity_m3_per_pmh * DAILY_HOURS,
        "loader": loader.productivity_m3_per_pmh * DAILY_HOURS,
    }


def _build_blocks(
    seed: int,
    *,
    num_blocks: int,
    num_days: int,
    landing_ids: Sequence[str],
    profiles: tuple[BlockProfile, ...],
    harvest_system_id: str | None,
    work_scale: float,
) -> tuple[list[BlockRecord], dict[str, dict[str, float]]]:
    rng = random.Random(seed)
    blocks: list[BlockRecord] = []
    rates: dict[str, dict[str, float]] = {}
    while len(blocks) < num_blocks:
        block, area, slope = _sample_block(
            rng,
            block_index=len(blocks),
            num_days=num_days,
            landing_ids=landing_ids,
            profiles=profiles,
            harvest_system_id=harvest_system_id,
            work_scale=work_scale,
        )
        blocks.append(block)
        rates[block.id] = _role_rates_for_block(
            block=block,
            area=area,
            slope=slope,
            landing_ids=landing_ids,
        )
    return blocks, rates


def _write_blocks(path: Path, blocks: Iterable[BlockRecord]) -> None:
    fieldnames = [
        "id",
        "landing_id",
        "harvest_system_id",
        "work_required",
        "earliest_start",
        "latest_finish",
        "avg_stem_size_m3",
        "volume_per_ha_m3",
        "stem_density_per_ha",
        "ground_slope_percent",
        "volume_per_ha_m3_sigma",
        "stem_density_per_ha_sigma",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for block in blocks:
            writer.writerow(block.to_row())


def _write_prod_rates(
    path: Path,
    *,
    blocks: Iterable[BlockRecord],
    role_rates: dict[str, dict[str, float]],
    machines_by_role: dict[str, list[str]],
) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["machine_id", "block_id", "rate"])
        writer.writeheader()
        for block in blocks:
            rates = role_rates[block.id]
            for role, machine_ids in machines_by_role.items():
                if role not in rates:
                    continue
                rate = round(rates[role], 6)
                for machine_id in machine_ids:
                    writer.writerow({"machine_id": machine_id, "block_id": block.id, "rate": rate})


def _write_machines(path: Path, machines_by_role: dict[str, list[str]]) -> None:
    defaults = {
        "feller_buncher": 1000.0,
        "grapple_skidder": 1100.0,
        "roadside_processor": 950.0,
        "loader": 900.0,
    }
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["id", "crew", "daily_hours", "operating_cost", "role"]
        )
        writer.writeheader()
        for role, machine_ids in machines_by_role.items():
            for idx, machine_id in enumerate(machine_ids, start=1):
                writer.writerow(
                    {
                        "id": machine_id,
                        "crew": f"C{machine_id}",
                        "daily_hours": DAILY_HOURS,
                        "operating_cost": round(
                            defaults.get(role, 1000.0) * (0.95 + 0.1 * (idx - 1)), 2
                        ),
                        "role": role,
                    }
                )


def _write_calendar(path: Path, machines: Iterable[str], num_days: int) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["machine_id", "day", "available"])
        writer.writeheader()
        for machine_id in machines:
            for day in range(1, num_days + 1):
                writer.writerow({"machine_id": machine_id, "day": day, "available": 1})


def _write_landings(path: Path, capacities: dict[str, int]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "daily_capacity"])
        writer.writeheader()
        for landing_id in sorted(capacities):
            writer.writerow({"id": landing_id, "daily_capacity": capacities[landing_id]})


def _write_distance_table(path: Path, block_ids: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["from_block", "to_block", "distance_m"])
        writer.writeheader()
        for prev in block_ids:
            for nxt in block_ids:
                if prev == nxt:
                    continue
                distance = 150 + 12 * abs(int(prev[1:]) - int(nxt[1:]))
                writer.writerow({"from_block": prev, "to_block": nxt, "distance_m": distance})


def _write_scenario_yaml(
    path: Path,
    *,
    config: DatasetConfig,
    distance_file: str,
    machines: Sequence[str],
) -> None:
    params = "\n".join(
        [
            f"  - machine_id: {mid}\n    walk_cost_per_meter: 0.02\n    move_cost_flat: 320\n"
            "    walk_threshold_m: 850\n    setup_cost: 50"
            for mid in machines
        ]
    )
    content = f"""name: FHOPS {config.label}
num_days: {config.num_days}
start_date: '{config.start_date}'
data:
  blocks: data/blocks.csv
  machines: data/machines.csv
  landings: data/landings.csv
  calendar: data/calendar.csv
  prod_rates: data/prod_rates.csv
  harvest_systems: data/harvest_systems.yaml
  mobilisation_distances: {distance_file}
mobilisation:
  default_walk_threshold_m: 900
  distance_csv: {distance_file}
  machine_params:
{params}
objective_weights:
  production: {OBJECTIVE_WEIGHTS["production"]}
  mobilisation: {OBJECTIVE_WEIGHTS["mobilisation"]}
"""
    path.write_text(content, encoding="utf-8")


def _write_readme(path: Path, config: DatasetConfig, blocks: Sequence[BlockRecord]) -> None:
    total_work = sum(block.work_required for block in blocks)
    large_blocks = sum(1 for block in blocks if _estimate_area_from_block(block) >= 12.0)
    roster = ", ".join(f"{role}={len(ids)}" for role, ids in config.machines_by_role.items())
    readme = dedent(
        f"""
        # FHOPS {config.label}

        - Planning horizon: {config.num_days} days
        - Blocks: {len(blocks)} (≈{total_work:,.0f} m³ total volume)
        - Large-block share (≥12 ha): {large_blocks}/{len(blocks)}
        - Machine roster: {roster}

        Synthetic blocks follow Lahrsen-aligned stand attributes and FHOPS productivity regressions
        (Lahrsen harvesters, ADV6N7 grapple skidders with area-derived skidding distance, Berry 2019
        processors, TN-261 loaders). Regenerate the dataset with:

        ```
        python scripts/rebuild_reference_datasets.py {config.name} --seed 20251209
        ```
        """
    ).strip()
    path.write_text(readme + "\n", encoding="utf-8")


def _write_harvest_systems_yaml(path: Path, config: DatasetConfig) -> None:
    role_counts = {role: len(ids) for role, ids in config.machines_by_role.items()}
    jobs = [
        {
            "name": job_name,
            "machine_role": machine_role,
            "prerequisites": list(prereqs),
        }
        for job_name, machine_role, prereqs in config.system_jobs
    ]
    payload = {
        config.harvest_system_id: {
            "system_id": config.harvest_system_id,
            "loader_batch_volume_m3": config.loader_batch_volume_m3,
            "role_headstart_shifts": dict(config.role_headstart_shifts),
            "role_counts": role_counts,
            "jobs": jobs,
        }
    }
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def rebuild_dataset(config: DatasetConfig, seed: int) -> None:
    scenario_dir = Path("examples") / config.name
    data_dir = scenario_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    blocks, role_rates = _build_blocks(
        seed,
        num_blocks=config.num_blocks,
        num_days=config.num_days,
        landing_ids=config.landing_ids,
        profiles=config.block_profiles,
        harvest_system_id=config.harvest_system_id,
        work_scale=config.work_scale,
    )
    _write_blocks(data_dir / "blocks.csv", blocks)
    _write_prod_rates(
        data_dir / "prod_rates.csv",
        blocks=blocks,
        role_rates=role_rates,
        machines_by_role=config.machines_by_role,
    )
    _write_machines(data_dir / "machines.csv", config.machines_by_role)
    machine_sequence = config.machine_sequence()
    _write_calendar(data_dir / "calendar.csv", machine_sequence, num_days=config.num_days)
    _write_landings(data_dir / "landings.csv", config.landing_capacities)
    _write_harvest_systems_yaml(data_dir / "harvest_systems.yaml", config)
    distance_file = f"{config.name}_block_distances.csv"
    _write_distance_table(scenario_dir / distance_file, [block.id for block in blocks])
    _write_scenario_yaml(
        scenario_dir / "scenario.yaml",
        config=config,
        distance_file=distance_file,
        machines=machine_sequence,
    )
    _write_readme(scenario_dir / "README.md", config, blocks)


SMALL_TIER_PROFILES = (
    BlockProfile(
        weight=0.6,
        area_range=(4.0, 10.0),
        avg_stem_range=(0.26, 0.46),
        volume_per_ha_range=(260.0, 340.0),
        slope_range=(6.0, 18.0),
        window_span=(3, 6),
    ),
    BlockProfile(
        weight=0.4,
        area_range=(1.0, 4.0),
        avg_stem_range=(0.16, 0.28),
        volume_per_ha_range=(180.0, 260.0),
        slope_range=(8.0, 24.0),
        window_span=(2, 4),
    ),
)

LADDER_PROFILES = (
    BlockProfile(
        weight=0.6,
        area_range=(10.0, 24.0),
        avg_stem_range=(0.32, 0.55),
        volume_per_ha_range=(230.0, 310.0),
        slope_range=(6.0, 16.0),
        window_span=(5, 9),
    ),
    BlockProfile(
        weight=0.25,
        area_range=(4.0, 10.0),
        avg_stem_range=(0.24, 0.38),
        volume_per_ha_range=(210.0, 290.0),
        slope_range=(8.0, 22.0),
        window_span=(4, 7),
    ),
    BlockProfile(
        weight=0.15,
        area_range=(1.5, 3.5),
        avg_stem_range=(0.15, 0.26),
        volume_per_ha_range=(150.0, 210.0),
        slope_range=(10.0, 25.0),
        window_span=(3, 5),
    ),
)


def _med42_machine_roster() -> dict[str, list[str]]:
    return {
        "feller_buncher": ["H1", "H2"],
        "grapple_skidder": ["H3"],
        "roadside_processor": ["H4", "H5", "H6"],
        "loader": ["H7", "H8", "H9"],
    }


def _large84_machine_roster() -> dict[str, list[str]]:
    return {
        "feller_buncher": ["H1", "H2", "H3", "H4"],
        "grapple_skidder": ["H5", "H6"],
        "roadside_processor": ["H7", "H8", "H9", "H10", "H11", "H12"],
        "loader": ["H13", "H14", "H15", "H16", "H17", "H18"],
    }


DATASET_CONFIGS = {
    "tiny7": DatasetConfig(
        name="tiny7",
        label="Tiny7",
        num_days=7,
        num_blocks=2,
        machines_by_role=_med42_machine_roster(),
        block_profiles=SMALL_TIER_PROFILES,
    ),
    "small21": DatasetConfig(
        name="small21",
        label="Small21",
        num_days=21,
        num_blocks=6,
        machines_by_role=_med42_machine_roster(),
        block_profiles=SMALL_TIER_PROFILES,
        work_scale=2.1,
    ),
    "med42": DatasetConfig(
        name="med42",
        label="Medium42",
        num_days=42,
        num_blocks=12,
        machines_by_role=_med42_machine_roster(),
        block_profiles=SMALL_TIER_PROFILES,
        work_scale=2.45,
    ),
    "large84": DatasetConfig(
        name="large84",
        label="Large84",
        num_days=84,
        num_blocks=48,
        machines_by_role=_large84_machine_roster(),
        block_profiles=SMALL_TIER_PROFILES,
        work_scale=5.8,
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset",
        nargs="?",
        default="tiny7",
        choices=sorted(DATASET_CONFIGS),
        help="Dataset to rebuild (default: tiny7).",
    )
    parser.add_argument("--seed", type=int, default=20251209, help="Random seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = DATASET_CONFIGS[args.dataset]
    rebuild_dataset(config, args.seed)
    print(f"Regenerated examples/{config.name} using seed {args.seed}")


if __name__ == "__main__":
    main()
