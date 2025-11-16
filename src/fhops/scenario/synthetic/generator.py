"""Synthetic scenario generator scaffolding."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypeVar, cast

import pandas as pd
import yaml

from fhops.costing.machine_rates import compose_default_rental_rate_for_role, normalize_machine_role
from fhops.evaluation.playback.events import SamplingConfig
from fhops.productivity import load_lahrsen_ranges
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    CrewAssignment,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scheduling.systems import HarvestSystem, default_system_registry
from fhops.scheduling.timeline import BlackoutWindow, ShiftDefinition, TimelineConfig

T = TypeVar("T")

_DEFAULT_TERRAIN_POOL = ["mixed"]
_DEFAULT_PRESCRIPTION_POOL = ["clearcut"]
_DEFAULT_CREW_POOL = ["crew-1", "crew-2"]
_DEFAULT_CAPABILITY_POOL = ["harvester", "forwarder"]
_LAHRSEN_RANGES = load_lahrsen_ranges()


def _default_operating_cost_for_role(role: str | None) -> float:
    canonical = normalize_machine_role(role)
    if not canonical:
        return 0.0
    composed = compose_default_rental_rate_for_role(canonical)
    if composed is None:
        return 0.0
    return round(composed[0], 2)


def _sample_metric(rng: random.Random, entry: dict[str, float]) -> float:
    lower = entry.get("min")
    upper = entry.get("max")
    if lower is None or upper is None:
        return float(entry.get("mean", 0.0))
    return round(rng.uniform(lower, upper), 3)


def _sample_block_metrics(rng: random.Random, section: str) -> dict[str, float]:
    ranges = _LAHRSEN_RANGES.get(section, _LAHRSEN_RANGES["daily"])
    avg_stem = _sample_metric(rng, ranges["avg_stem_size_m3"])
    volume = _sample_metric(rng, ranges["volume_per_ha_m3"])
    density = _sample_metric(rng, ranges["stem_density_per_ha"])
    slope = _sample_metric(rng, ranges["ground_slope_percent"])

    def _sigma(val: float) -> float:
        return round(max(val * 0.2, 0.0), 3)

    return {
        "avg_stem_size_m3": avg_stem,
        "volume_per_ha_m3": volume,
        "volume_per_ha_m3_sigma": _sigma(volume),
        "stem_density_per_ha": density,
        "stem_density_per_ha_sigma": _sigma(density),
        "ground_slope_percent": slope,
    }


def _sequence_list(value: object | None, fallback: Sequence[T]) -> list[T]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [cast(T, item) for item in value]
    return list(fallback)


def _maybe_numeric_dict(value: object | None) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    typed: dict[str, float] = {}
    for key, raw in value.items():
        if isinstance(raw, int | float):
            typed[str(key)] = float(raw)
    return typed


@dataclass
class SyntheticScenarioSpec:
    """Configuration for generating synthetic scenarios."""

    num_blocks: int
    num_days: int
    num_machines: int
    landing_capacity: int = 1
    blackout_days: list[int] | None = None


def generate_basic(spec: SyntheticScenarioSpec) -> Scenario:
    """Generate a minimal scenario matching the supplied specification."""

    blocks = [
        Block(
            id=f"B{i + 1}",
            landing_id="L1",
            work_required=10.0,
            earliest_start=1,
            latest_finish=spec.num_days,
        )
        for i in range(spec.num_blocks)
    ]
    machines = [Machine(id=f"M{i + 1}") for i in range(spec.num_machines)]
    landings = [Landing(id="L1", daily_capacity=spec.landing_capacity)]
    calendar = [
        CalendarEntry(machine_id=machine.id, day=day, available=1)
        for machine in machines
        for day in range(1, spec.num_days + 1)
    ]
    production_rates = [
        ProductionRate(machine_id=machine.id, block_id=block.id, rate=10.0)
        for machine in machines
        for block in blocks
    ]

    timeline = None
    if spec.blackout_days is not None:
        shift = ShiftDefinition(name="day", hours=10.0, shifts_per_day=1)
        blackouts = [
            BlackoutWindow(start_day=day, end_day=day, reason="synthetic-blackout")
            for day in spec.blackout_days
        ]
        timeline = TimelineConfig(shifts=[shift], blackouts=blackouts)

    return Scenario(
        name="synthetic-basic",
        num_days=spec.num_days,
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        production_rates=production_rates,
        timeline=timeline,
    )


def generate_with_systems(
    spec: SyntheticScenarioSpec,
    systems: dict[str, HarvestSystem] | None = None,
) -> Scenario:
    """Generate a scenario and assign blocks round-robin to harvest systems."""

    if systems is None:
        systems = dict(default_system_registry())
    system_ids = list(systems.keys())
    if not system_ids:
        raise ValueError("At least one harvest system is required")

    base = generate_basic(spec)
    roles = sorted({job.machine_role for system in systems.values() for job in system.jobs})
    if roles:
        machines = [
            machine.model_copy(update={"role": roles[idx % len(roles)]})
            for idx, machine in enumerate(base.machines)
        ]
    else:
        machines = base.machines
    blocks = []
    for idx, block in enumerate(base.blocks):
        system_id = system_ids[idx % len(system_ids)]
        blocks.append(block.model_copy(update={"harvest_system_id": system_id}))

    return base.model_copy(
        update={"blocks": blocks, "machines": machines, "harvest_systems": systems}
    )


def _as_range(value: tuple[int, int] | int) -> tuple[int, int]:
    if isinstance(value, tuple):
        return value
    return (value, value)


def _weighted_choice(
    rng: random.Random, pool: list[str], weights: list[float] | None
) -> str | None:
    if not pool:
        return None
    if weights and len(weights) == len(pool):
        return rng.choices(pool, weights=weights, k=1)[0]
    return rng.choice(pool)


def _normalise_mix(mix: dict[str, float]) -> dict[str, float]:
    total = sum(value for value in mix.values() if value >= 0)
    if total == 0:
        return {key: 1.0 / len(mix) for key in mix}
    return {key: value / total if value >= 0 else 0.0 for key, value in mix.items()}


def _deep_merge(base: dict[str, object], updates: dict[str, object]) -> dict[str, object]:
    result = deepcopy(base)
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


@dataclass
class BlackoutBias:
    """Bias blackout probabilities for specific windows."""

    start_day: int
    end_day: int
    probability: float
    duration: tuple[int, int] | int | None = None


@dataclass
class SyntheticDatasetConfig:
    """Configuration for generating random synthetic datasets."""

    name: str
    num_blocks: tuple[int, int] | int
    num_days: tuple[int, int] | int
    num_machines: tuple[int, int] | int
    num_landings: tuple[int, int] | int = 1
    shift_hours: tuple[float, float] = (8.0, 12.0)
    shifts_per_day: int = 1
    machine_daily_hours: float = 24.0
    landing_capacity: tuple[int, int] | int = (1, 3)
    work_required: tuple[float, float] = (6.0, 18.0)
    production_rate: tuple[float, float] = (6.0, 18.0)
    availability_probability: float = 0.9
    blackout_probability: float = 0.1
    blackout_duration: tuple[int, int] | int = (1, 2)
    role_pool: list[str] = field(default_factory=lambda: ["harvester", "forwarder"])
    tier: str | None = None
    terrain_pool: list[str] = field(default_factory=lambda: list(_DEFAULT_TERRAIN_POOL))
    terrain_weights: list[float] | None = None
    prescription_pool: list[str] = field(default_factory=lambda: list(_DEFAULT_PRESCRIPTION_POOL))
    prescription_weights: list[float] | None = None
    crew_pool: list[str] = field(default_factory=lambda: list(_DEFAULT_CREW_POOL))
    capability_pool: list[str] = field(default_factory=lambda: list(_DEFAULT_CAPABILITY_POOL))
    crew_capability_span: tuple[int, int] = (1, 2)
    system_mix: dict[str, float] | None = None
    blackout_biases: list[BlackoutBias] = field(default_factory=list)
    sampling_overrides: dict[str, object] | None = None
    block_metric_section: str = "daily"


@dataclass
class SyntheticDatasetBundle:
    """Container for generated scenario tables and helpers to persist them."""

    scenario: Scenario
    blocks: pd.DataFrame
    machines: pd.DataFrame
    landings: pd.DataFrame
    calendar: pd.DataFrame
    production_rates: pd.DataFrame
    metadata: dict[str, object] | None = None

    def write(
        self,
        out_dir: Path,
        *,
        include_yaml: bool = True,
        metadata_path: Path | None = None,
    ) -> Path:
        out_dir = Path(out_dir)
        data_dir = out_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        self.blocks.to_csv(data_dir / "blocks.csv", index=False)
        self.machines.to_csv(data_dir / "machines.csv", index=False)
        self.landings.to_csv(data_dir / "landings.csv", index=False)
        self.calendar.to_csv(data_dir / "calendar.csv", index=False)
        self.production_rates.to_csv(data_dir / "prod_rates.csv", index=False)

        scenario_path = out_dir / "scenario.yaml"
        if include_yaml:
            data_section: dict[str, str] = {
                "blocks": "data/blocks.csv",
                "machines": "data/machines.csv",
                "landings": "data/landings.csv",
                "calendar": "data/calendar.csv",
                "prod_rates": "data/prod_rates.csv",
            }
            if self.scenario.crew_assignments is not None:
                crew_path = data_dir / "crew_assignments.csv"
                crew_records = [
                    assignment.model_dump(exclude_none=True)
                    for assignment in self.scenario.crew_assignments
                ]
                pd.DataFrame.from_records(crew_records).to_csv(crew_path, index=False)
                data_section["crew_assignments"] = "data/crew_assignments.csv"
            payload: dict[str, object] = {
                "name": self.scenario.name,
                "num_days": self.scenario.num_days,
                "schema_version": self.scenario.schema_version,
                "data": data_section,
            }
            if self.scenario.timeline is not None:
                payload["timeline"] = self.scenario.timeline.model_dump(exclude_none=True)
            if self.scenario.harvest_systems is not None:
                payload["harvest_systems"] = {
                    key: asdict(system) for key, system in self.scenario.harvest_systems.items()
                }
            if self.scenario.objective_weights is not None:
                payload["objective_weights"] = self.scenario.objective_weights.model_dump(
                    exclude_none=True
                )
            if self.scenario.mobilisation is not None:
                payload["mobilisation"] = self.scenario.mobilisation.model_dump(exclude_none=True)

            with scenario_path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle, sort_keys=False)
        meta_out = metadata_path
        if meta_out is None and self.metadata is not None:
            meta_out = out_dir / "metadata.yaml"
        if meta_out is not None and self.metadata is not None:
            with Path(meta_out).open("w", encoding="utf-8") as handle:
                yaml.safe_dump(self.metadata, handle, sort_keys=False)
        return scenario_path


TIER_DEFAULTS: dict[str, dict[str, object]] = {
    "small": {
        "terrain_pool": ["gentle", "mixed"],
        "terrain_weights": [0.7, 0.3],
        "prescription_pool": ["thinning", "selection"],
        "prescription_weights": [0.6, 0.4],
        "crew_pool": ["crew-1", "crew-2"],
        "capability_pool": ["harvester", "forwarder"],
        "crew_capability_span": (1, 1),
        "blackout_probability": 0.0,
        "blackout_duration": (1, 1),
        "blackout_biases": [],
    },
    "medium": {
        "terrain_pool": ["rolling", "mixed", "steep"],
        "terrain_weights": [0.2, 0.6, 0.2],
        "prescription_pool": ["clearcut", "thinning"],
        "prescription_weights": [0.35, 0.65],
        "crew_pool": ["crew-1", "crew-2", "crew-3"],
        "capability_pool": ["harvester", "forwarder", "processor"],
        "crew_capability_span": (1, 2),
        "blackout_probability": 0.12,
        "blackout_duration": (1, 2),
        "blackout_biases": [
            BlackoutBias(start_day=8, end_day=10, probability=0.35, duration=(1, 2)),
        ],
    },
    "large": {
        "terrain_pool": ["steep", "mixed", "snow"],
        "terrain_weights": [0.35, 0.4, 0.25],
        "prescription_pool": ["clearcut", "variable_retention"],
        "prescription_weights": [0.5, 0.5],
        "crew_pool": ["crew-1", "crew-2", "crew-3", "crew-4"],
        "capability_pool": ["harvester", "forwarder", "processor", "grader"],
        "crew_capability_span": (2, 3),
        "blackout_probability": 0.2,
        "blackout_duration": (2, 3),
        "blackout_biases": [
            BlackoutBias(start_day=5, end_day=7, probability=0.4, duration=(2, 3)),
            BlackoutBias(start_day=12, end_day=14, probability=0.35, duration=(2, 3)),
        ],
        "system_mix": {"ground_fb_skid": 0.4, "ctl": 0.35, "steep_tethered": 0.25},
    },
}

SAMPLING_PRESETS: dict[str, dict[str, object]] = {
    "small": {
        "samples": 6,
        "downtime": {"enabled": False, "probability": 0.0},
        "weather": {"enabled": False, "day_probability": 0.0, "severity_levels": {}},
        "landing": {"enabled": False, "probability": 0.0},
    },
    "medium": {
        "samples": 12,
        "downtime": {
            "enabled": True,
            "probability": 0.12,
            "mean_duration_hours": 3.0,
            "std_duration_hours": 1.0,
            "max_concurrent": 1,
        },
        "weather": {
            "enabled": True,
            "day_probability": 0.25,
            "severity_levels": {"moderate": 0.6, "severe": 0.4},
            "impact_window_days": 2,
        },
        "landing": {
            "enabled": True,
            "probability": 0.18,
            "capacity_multiplier_range": (0.45, 0.75),
            "duration_days": 2,
        },
    },
    "large": {
        "samples": 18,
        "downtime": {
            "enabled": True,
            "probability": 0.2,
            "mean_duration_hours": 5.0,
            "std_duration_hours": 2.0,
            "max_concurrent": 2,
        },
        "weather": {
            "enabled": True,
            "day_probability": 0.35,
            "severity_levels": {"moderate": 0.4, "severe": 0.6},
            "impact_window_days": 3,
        },
        "landing": {
            "enabled": True,
            "probability": 0.25,
            "capacity_multiplier_range": (0.35, 0.7),
            "duration_days": 3,
        },
    },
}


def sampling_config_for(config: SyntheticDatasetConfig) -> SamplingConfig:
    base = SamplingConfig(samples=10)
    tier_key = (config.tier or "").lower()
    preset_updates = SAMPLING_PRESETS.get(tier_key, {})
    data = base.model_dump()
    if preset_updates:
        data = _deep_merge(data, preset_updates)
    if config.sampling_overrides:
        data = _deep_merge(data, config.sampling_overrides)
    return SamplingConfig.model_validate(data)


def _sample_int(rng: random.Random, bounds: tuple[int, int] | int) -> int:
    low, high = _as_range(bounds)
    return rng.randint(int(low), int(high))


def _sample_float(rng: random.Random, bounds: tuple[float, float]) -> float:
    return rng.uniform(float(bounds[0]), float(bounds[1]))


def generate_random_dataset(
    config: SyntheticDatasetConfig,
    *,
    seed: int = 123,
    systems: dict[str, HarvestSystem] | None = None,
) -> SyntheticDatasetBundle:
    """Generate a random synthetic dataset bundle (scenario + CSV tables)."""

    rng = random.Random(seed)
    feature_rng = random.Random(seed + 10_001)
    tier_defaults = TIER_DEFAULTS.get((config.tier or "").lower(), {})
    num_blocks = _sample_int(rng, config.num_blocks)
    num_days = _sample_int(rng, config.num_days)
    num_machines = _sample_int(rng, config.num_machines)
    num_landings = max(1, _sample_int(rng, config.num_landings))

    landing_ids = [f"L{i + 1}" for i in range(num_landings)]
    default_blackout_prob = SyntheticDatasetConfig.__dataclass_fields__[
        "blackout_probability"
    ].default
    blackout_probability = config.blackout_probability
    if config.blackout_probability == default_blackout_prob:
        prob_candidate = tier_defaults.get("blackout_probability")
        if isinstance(prob_candidate, int | float):
            blackout_probability = float(prob_candidate)

    default_blackout_duration = SyntheticDatasetConfig.__dataclass_fields__[
        "blackout_duration"
    ].default
    blackout_duration: tuple[int, int] | int = config.blackout_duration
    if config.blackout_duration == default_blackout_duration:
        duration_candidate = tier_defaults.get("blackout_duration")
        if isinstance(duration_candidate, tuple) and len(duration_candidate) >= 2:
            blackout_duration = (int(duration_candidate[0]), int(duration_candidate[1]))
        elif isinstance(duration_candidate, int):
            blackout_duration = int(duration_candidate)

    terrain_pool = _sequence_list(tier_defaults.get("terrain_pool"), config.terrain_pool)
    if config.terrain_pool and config.terrain_pool != _DEFAULT_TERRAIN_POOL:
        terrain_pool = list(config.terrain_pool)
    terrain_weights: list[float] | None = None
    default_terrain_weights = tier_defaults.get("terrain_weights")
    if isinstance(default_terrain_weights, Sequence) and not isinstance(
        default_terrain_weights, str | bytes
    ):
        terrain_weights = [float(weight) for weight in default_terrain_weights]
    if config.terrain_weights is not None:
        terrain_weights = [float(weight) for weight in config.terrain_weights]

    prescription_pool = _sequence_list(
        tier_defaults.get("prescription_pool"), config.prescription_pool
    )
    if config.prescription_pool and config.prescription_pool != _DEFAULT_PRESCRIPTION_POOL:
        prescription_pool = list(config.prescription_pool)
    prescription_weights: list[float] | None = None
    default_prescription_weights = tier_defaults.get("prescription_weights")
    if isinstance(default_prescription_weights, Sequence) and not isinstance(
        default_prescription_weights, str | bytes
    ):
        prescription_weights = [float(weight) for weight in default_prescription_weights]
    if config.prescription_weights is not None:
        prescription_weights = [float(weight) for weight in config.prescription_weights]

    crew_pool = _sequence_list(tier_defaults.get("crew_pool"), config.crew_pool)
    if config.crew_pool and config.crew_pool != _DEFAULT_CREW_POOL:
        crew_pool = list(config.crew_pool)

    capability_source = tier_defaults.get("capability_pool")
    capability_pool = _sequence_list(
        capability_source, config.capability_pool or config.role_pool or []
    )
    if config.capability_pool and config.capability_pool != _DEFAULT_CAPABILITY_POOL:
        capability_pool = list(config.capability_pool)

    crew_capability_span = config.crew_capability_span
    default_span = SyntheticDatasetConfig.__dataclass_fields__["crew_capability_span"].default
    if crew_capability_span == default_span:
        span_candidate = tier_defaults.get("crew_capability_span")
        if isinstance(span_candidate, Sequence):
            try:
                crew_capability_span = (int(span_candidate[0]), int(span_candidate[1]))
            except (IndexError, TypeError, ValueError):
                crew_capability_span = config.crew_capability_span

    blackout_biases: list[BlackoutBias] = []
    default_biases = tier_defaults.get("blackout_biases")
    if isinstance(default_biases, Sequence):
        parsed_biases: list[BlackoutBias] = []
        for bias in default_biases:
            if isinstance(bias, BlackoutBias):
                parsed_biases.append(bias)
            elif isinstance(bias, dict):
                parsed_biases.append(BlackoutBias(**bias))
        blackout_biases = parsed_biases
    if config.blackout_biases:
        blackout_biases = list(config.blackout_biases)

    system_mix: dict[str, float] | None = None
    if config.system_mix is not None:
        system_mix = dict(config.system_mix)
    else:
        system_mix = _maybe_numeric_dict(tier_defaults.get("system_mix"))
    normalised_mix = _normalise_mix(system_mix) if system_mix else None
    blocks_records: list[dict[str, object]] = []
    for idx in range(num_blocks):
        landing_id = rng.choice(landing_ids)
        work_required = round(_sample_float(rng, config.work_required), 3)
        earliest = rng.randint(1, num_days)
        latest = rng.randint(earliest, num_days)
        terrain = (
            _weighted_choice(feature_rng, terrain_pool, terrain_weights) if terrain_pool else None
        )
        prescription = (
            _weighted_choice(feature_rng, prescription_pool, prescription_weights)
            if prescription_pool
            else None
        )
        stand_metrics = _sample_block_metrics(feature_rng, config.block_metric_section)
        blocks_records.append(
            {
                "id": f"B{idx + 1}",
                "landing_id": landing_id,
                "work_required": work_required,
                "earliest_start": earliest,
                "latest_finish": latest,
                **stand_metrics,
                **({"terrain": terrain} if terrain is not None else {}),
                **({"prescription": prescription} if prescription is not None else {}),
            }
        )

    role_pool = config.role_pool or []
    machines_records: list[dict[str, object]] = []
    base_crews = crew_pool or [f"crew-{idx + 1}" for idx in range(num_machines)]
    crew_capabilities: dict[str, list[str]] = {}
    base_capabilities: dict[str, list[str]] = {}
    if base_crews:
        span_low, span_high = crew_capability_span
        span_low = max(0, int(span_low))
        span_high = max(span_low, int(span_high))
        max_pick = len(capability_pool)
        for base in base_crews:
            if base in base_capabilities:
                continue
            if max_pick == 0 or span_high == 0:
                base_capabilities[base] = []
                continue
            pick_low = min(max_pick, span_low)
            pick_high = min(max_pick, span_high)
            if pick_high <= 0:
                base_capabilities[base] = []
                continue
            lower = pick_low if pick_low > 0 else 1
            pick = feature_rng.randint(lower, pick_high)
            pick = max(1 if pick_low > 0 else 0, pick)
            pick = min(max_pick, pick)
            if pick == 0:
                base_capabilities[base] = []
                continue
            base_capabilities[base] = sorted(feature_rng.sample(capability_pool, k=pick))
    crew_ids: list[str] = []
    if base_crews:
        counts: dict[str, int] = {}
        for idx in range(num_machines):
            base = base_crews[idx % len(base_crews)]
            counts[base] = counts.get(base, 0) + 1
            if counts[base] == 1 and base not in crew_ids and len(base_crews) >= num_machines:
                crew_id = base
            elif counts[base] == 1 and base not in crew_ids and len(base_crews) >= counts[base]:
                crew_id = base
            else:
                crew_id = f"{base}-{counts[base]}"
                while crew_id in crew_ids:
                    counts[base] += 1
                    crew_id = f"{base}-{counts[base]}"
            crew_ids.append(crew_id)
            crew_capabilities[crew_id] = list(base_capabilities.get(base, []))
    for idx in range(num_machines):
        raw_role = role_pool[idx % len(role_pool)] if role_pool else None
        role = normalize_machine_role(raw_role)
        assigned_crew = crew_ids[idx] if crew_ids else None
        rental_rate = _default_operating_cost_for_role(role)
        machines_records.append(
            {
                "id": f"M{idx + 1}",
                "role": role,
                "crew": assigned_crew,
                "daily_hours": float(config.machine_daily_hours),
                "operating_cost": rental_rate,
            }
        )

    landings_records = [
        {
            "id": landing_id,
            "daily_capacity": max(1, _sample_int(rng, config.landing_capacity)),
        }
        for landing_id in landing_ids
    ]

    calendar_records: list[dict[str, object]] = []
    for machine_record in machines_records:
        for day in range(1, num_days + 1):
            available = 1 if rng.random() <= config.availability_probability else 0
            calendar_records.append(
                {
                    "machine_id": machine_record["id"],
                    "day": day,
                    "available": available,
                }
            )

    production_records: list[dict[str, object]] = []
    for machine_record in machines_records:
        for block_record in blocks_records:
            rate = round(_sample_float(rng, config.production_rate), 3)
            production_records.append(
                {
                    "machine_id": machine_record["id"],
                    "block_id": block_record["id"],
                    "rate": rate,
                }
            )

    shift_def = ShiftDefinition(
        name="S1",
        hours=float(_sample_float(rng, config.shift_hours)),
        shifts_per_day=config.shifts_per_day,
    )
    blackouts: list[BlackoutWindow] = []
    day_cursor = 1
    while day_cursor <= num_days:
        day_probability = blackout_probability
        duration_bounds: tuple[int, int] | int = blackout_duration
        for bias in blackout_biases:
            if bias.start_day <= day_cursor <= bias.end_day:
                day_probability = max(day_probability, bias.probability)
                if bias.duration is not None:
                    if isinstance(bias.duration, tuple):
                        duration_bounds = (int(bias.duration[0]), int(bias.duration[1]))
                    else:
                        duration_bounds = int(bias.duration)
        if rng.random() <= day_probability:
            duration = max(1, _sample_int(rng, duration_bounds))
            blackouts.append(
                BlackoutWindow(
                    start_day=day_cursor,
                    end_day=min(num_days, day_cursor + duration - 1),
                    reason="synthetic-blackout",
                )
            )
            day_cursor += duration
        else:
            day_cursor += 1
    timeline = TimelineConfig(shifts=[shift_def], blackouts=blackouts)

    blocks = [Block(**cast(dict[str, Any], record)) for record in blocks_records]
    machines = [Machine(**cast(dict[str, Any], record)) for record in machines_records]
    landings = [Landing(**cast(dict[str, Any], record)) for record in landings_records]
    calendar = [CalendarEntry(**cast(dict[str, Any], record)) for record in calendar_records]
    production_rates = [
        ProductionRate(**cast(dict[str, Any], record)) for record in production_records
    ]

    crew_assignment_models: list[CrewAssignment] | None = None
    if crew_pool:
        assignments: list[CrewAssignment] = []
        for machine in machines:
            crew_id_value = machine.crew
            if crew_id_value is None:
                continue
            crew_id = str(crew_id_value)
            capabilities = crew_capabilities.get(crew_id, [])
            notes = None
            if capabilities:
                notes = f"capabilities={','.join(capabilities)}"
            assignments.append(
                CrewAssignment(
                    crew_id=crew_id,
                    machine_id=machine.id,
                    primary_role=machine.role,
                    notes=notes,
                )
            )
        crew_assignment_models = assignments or None

    scenario = Scenario(
        name=config.name,
        num_days=num_days,
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        production_rates=production_rates,
        timeline=timeline,
        crew_assignments=crew_assignment_models,
    )

    if systems is None:
        systems = {}
    if systems:
        roles = sorted({job.machine_role for system in systems.values() for job in system.jobs})
        if roles:
            updated_machines = [
                machine.model_copy(
                    update={
                        "role": normalize_machine_role(roles[idx % len(roles)]),
                        "operating_cost": _default_operating_cost_for_role(roles[idx % len(roles)]),
                    }
                )
                for idx, machine in enumerate(scenario.machines)
            ]
            scenario = scenario.model_copy(update={"machines": updated_machines})
        updated_blocks = []
        system_ids = list(systems.keys())
        system_weights = None
        if normalised_mix:
            available_mix = {key: normalised_mix.get(key, 0.0) for key in system_ids}
            if any(weight > 0 for weight in available_mix.values()):
                system_weights = [available_mix[system_id] for system_id in system_ids]
            # zero-weight fallback -> round robin
        for idx, block in enumerate(scenario.blocks):
            if system_weights:
                system_id = feature_rng.choices(system_ids, weights=system_weights, k=1)[0]
            else:
                system_id = system_ids[idx % len(system_ids)]
            updated_blocks.append(block.model_copy(update={"harvest_system_id": system_id}))
        scenario = scenario.model_copy(
            update={"blocks": updated_blocks, "harvest_systems": systems}
        )

    sampling_config = sampling_config_for(config)

    metadata: dict[str, object] = {
        "name": config.name,
        "tier": (config.tier or "custom"),
        "seed": seed,
        "counts": {
            "blocks": len(blocks_records),
            "machines": len(machines_records),
            "landings": len(landings_records),
            "calendar": len(calendar_records),
            "production_rates": len(production_records),
        },
        "terrain_counts": dict(
            Counter(
                record.get("terrain")
                for record in blocks_records
                if record.get("terrain") is not None
            )
        ),
        "prescription_counts": dict(
            Counter(
                record.get("prescription")
                for record in blocks_records
                if record.get("prescription") is not None
            )
        ),
        "crew_capabilities": crew_capabilities,
        "blackouts": [blackout.model_dump(exclude_none=True) for blackout in blackouts],
        "shifts_per_day": config.shifts_per_day,
        "shift_hours": shift_def.hours,
        "terrain_profile": {
            "values": terrain_pool,
            "weights": terrain_weights,
        },
        "prescription_profile": {
            "values": prescription_pool,
            "weights": prescription_weights,
        },
        "system_mix": normalised_mix,
        "blackout_biases": [
            {
                "start_day": bias.start_day,
                "end_day": bias.end_day,
                "probability": bias.probability,
                "duration": bias.duration,
            }
            for bias in blackout_biases
        ],
        "sampling_config": sampling_config.model_dump(),
    }

    return SyntheticDatasetBundle(
        scenario=scenario,
        blocks=pd.DataFrame.from_records(blocks_records),
        machines=pd.DataFrame.from_records(machines_records),
        landings=pd.DataFrame.from_records(landings_records),
        calendar=pd.DataFrame.from_records(calendar_records),
        production_rates=pd.DataFrame.from_records(production_records),
        metadata=metadata,
    )


__all__ = [
    "SyntheticScenarioSpec",
    "SyntheticDatasetConfig",
    "SyntheticDatasetBundle",
    "BlackoutBias",
    "SAMPLING_PRESETS",
    "generate_basic",
    "generate_with_systems",
    "generate_random_dataset",
]
