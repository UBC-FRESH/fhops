#!/usr/bin/env python3
"""Regenerate the med42 dataset with Lahrsen-aligned big-block mixes."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import random
from typing import Iterable

from fhops.productivity import (
    ADV6N7DeckingMode,
    LahrsenModel,
    estimate_grapple_skidder_productivity_adv6n7,
    estimate_loader_forwarder_productivity_tn261,
    estimate_processor_productivity_berry2019,
    estimate_productivity,
)

MACHINES = ("H1", "H2", "H3", "H4")
LANDINGS = ("L1", "L2", "L3", "L4")
DAILY_HOURS = 24.0


@dataclass
class BlockRecord:
    id: str
    landing_id: str
    work_required: float
    earliest_start: int
    latest_finish: int
    avg_stem_size_m3: float
    volume_per_ha_m3: float
    stem_density_per_ha: float
    ground_slope_percent: float
    volume_per_ha_m3_sigma: float
    stem_density_per_ha_sigma: float


@dataclass
class ProductivityRecord:
    machine_id: str
    block_id: str
    rate: float


@dataclass
class DatasetStats:
    total_volume: float
    large_volume: float
    large_block_count: int
    small_block_count: int
    machine_days: dict[str, float]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _choose_category(
    rng: random.Random,
    *,
    current_share: float,
    target_share: float,
    large_blocks: int,
    small_blocks: int,
) -> str:
    if current_share < target_share:
        return "large"
    if small_blocks == 0:
        return "small"
    if large_blocks == 0:
        return "large"
    if current_share > target_share + 0.08:
        return "small"
    return "large" if rng.random() < 0.5 else "small"


def _sigma(value: float) -> float:
    return round(value * 0.2, 6)


def _sample_block(
    rng: random.Random,
    *,
    block_index: int,
    category: str,
) -> tuple[BlockRecord, float, float]:
    landing = LANDINGS[block_index % len(LANDINGS)]
    if category == "large":
        area = rng.uniform(10.0, 18.0)
        avg_stem = rng.uniform(0.32, 0.6)
        volume_per_ha = rng.uniform(320.0, 360.0)
        slope = rng.uniform(6.0, 22.0)
        window = rng.randint(9, 16)
    else:
        area = rng.uniform(1.3, 2.3)
        avg_stem = rng.uniform(0.12, 0.24)
        volume_per_ha = rng.uniform(140.0, 190.0)
        slope = rng.uniform(10.0, 30.0)
        window = rng.randint(6, 12)
    stem_density = volume_per_ha / avg_stem
    work_required = area * volume_per_ha
    earliest = rng.randint(1, 32)
    latest = min(42, earliest + window)
    if latest <= earliest:
        latest = min(42, earliest + 2)
    record = BlockRecord(
        id=f"B{block_index + 1:02d}",
        landing_id=landing,
        work_required=round(work_required, 6),
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


def _machine_rates_for_block(
    *,
    block: BlockRecord,
    area: float,
    slope: float,
    rng: random.Random,
) -> dict[str, float]:
    landing_idx = LANDINGS.index(block.landing_id)
    distance = _clamp(
        180.0 + area * 4.0 + rng.uniform(-30.0, 30.0) + landing_idx * 35.0, 150.0, 620.0
    )
    loader_distance = _clamp(distance * 0.6, 80.0, 360.0)

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
    rates = {
        "H1": fb.predicted_m3_per_pmh * DAILY_HOURS,
        "H2": skidder.productivity_m3_per_pmh * DAILY_HOURS,
        "H3": processor.productivity_m3_per_pmh * DAILY_HOURS,
        "H4": loader.productivity_m3_per_pmh * DAILY_HOURS,
    }
    if min(rates.values()) <= 0:
        raise ValueError("Non-positive productivity encountered")
    return rates


def _build_dataset(
    *,
    seed: int,
    min_blocks: int,
    target_bottleneck_days: float,
    large_share: float,
    max_blocks: int,
    max_large_blocks: int,
) -> tuple[list[BlockRecord], list[ProductivityRecord], DatasetStats]:
    rng = random.Random(seed)
    blocks: list[BlockRecord] = []
    prod_rows: list[ProductivityRecord] = []
    total_volume = 0.0
    large_volume = 0.0
    large_blocks = 0
    small_blocks = 0
    machine_days = {machine: 0.0 for machine in MACHINES}

    while len(blocks) < max_blocks:
        share = large_volume / total_volume if total_volume > 0 else 0.0
        if large_blocks >= max_large_blocks:
            category = "small"
        else:
            category = _choose_category(
                rng,
                current_share=share,
                target_share=large_share,
                large_blocks=large_blocks,
                small_blocks=small_blocks,
            )
        block, area, slope = _sample_block(rng, block_index=len(blocks), category=category)
        try:
            rates = _machine_rates_for_block(block=block, area=area, slope=slope, rng=rng)
        except ValueError:
            continue
        blocks.append(block)
        total_volume += block.work_required
        if category == "large":
            large_volume += block.work_required
            large_blocks += 1
        else:
            small_blocks += 1
        for machine_id, rate in rates.items():
            prod_rows.append(
                ProductivityRecord(
                    machine_id=machine_id,
                    block_id=block.id,
                    rate=round(rate, 6),
                )
            )
            machine_days[machine_id] += block.work_required / rate
        bottleneck = max(machine_days.values())
        share = large_volume / total_volume if total_volume else 0.0
        if (
            len(blocks) >= min_blocks
            and share >= large_share
            and bottleneck >= target_bottleneck_days
        ):
            break
    else:
        raise RuntimeError("Reached max_blocks before hitting bottleneck/large-share targets")

    stats = DatasetStats(
        total_volume=total_volume,
        large_volume=large_volume,
        large_block_count=large_blocks,
        small_block_count=small_blocks,
        machine_days=machine_days,
    )
    return blocks, prod_rows, stats


def _write_blocks(path: Path, blocks: Iterable[BlockRecord]) -> None:
    fieldnames = [
        "id",
        "landing_id",
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
            writer.writerow(block.__dict__)


def _write_prod_rates(path: Path, rows: Iterable[ProductivityRecord]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["machine_id", "block_id", "rate"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20251209, help="Random seed.")
    parser.add_argument(
        "--min-blocks",
        type=int,
        default=24,
        help="Minimum number of blocks before we start testing capacity targets.",
    )
    parser.add_argument(
        "--target-bottleneck-days",
        type=float,
        default=46.0,
        help="Stop once the busiest machine requires at least this many days.",
    )
    parser.add_argument(
        "--large-share",
        type=float,
        default=0.6,
        help="Target share of total volume carried by ~20 ha blocks.",
    )
    parser.add_argument(
        "--max-blocks",
        type=int,
        default=64,
        help="Safety cap to avoid infinite loops.",
    )
    parser.add_argument(
        "--max-large-blocks",
        type=int,
        default=3,
        help="Upper bound on 20 ha-class blocks to keep total volume realistic.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "examples" / "med42" / "data",
        help="Directory containing blocks.csv and prod_rates.csv.",
    )
    args = parser.parse_args()
    blocks, prod_rows, stats = _build_dataset(
        seed=args.seed,
        min_blocks=args.min_blocks,
        target_bottleneck_days=args.target_bottleneck_days,
        large_share=args.large_share,
        max_blocks=args.max_blocks,
        max_large_blocks=args.max_large_blocks,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_blocks(args.output_dir / "blocks.csv", blocks)
    _write_prod_rates(args.output_dir / "prod_rates.csv", prod_rows)

    bottleneck_machine = max(stats.machine_days, key=stats.machine_days.get)
    large_share = stats.large_volume / stats.total_volume if stats.total_volume else 0.0
    print(
        f"Blocks: {len(blocks)} (large={stats.large_block_count}, small={stats.small_block_count})"
    )
    print(f"Total volume: {stats.total_volume:,.1f} m3")
    print(f"Large-block share: {large_share:.1%}")
    print(f"Bottleneck: {stats.machine_days[bottleneck_machine]:.2f} days on {bottleneck_machine}")


if __name__ == "__main__":
    main()
