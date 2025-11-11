"""Synthetic scenario generator scaffolding."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

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


TIER_DEFAULTS: dict[str, dict[str, object]] = {
    "small": {
        "terrain_pool": ["gentle", "mixed"],
        "prescription_pool": ["thinning", "selection"],
        "crew_pool": ["crew-1", "crew-2"],
        "capability_pool": ["harvester", "forwarder"],
        "crew_capability_span": (1, 1),
        "blackout_probability": 0.0,
        "blackout_duration": (1, 1),
    },
    "medium": {
        "terrain_pool": ["rolling", "mixed", "steep"],
        "prescription_pool": ["clearcut", "thinning"],
        "crew_pool": ["crew-1", "crew-2", "crew-3"],
        "capability_pool": ["harvester", "forwarder", "processor"],
        "crew_capability_span": (1, 2),
        "blackout_probability": 0.12,
        "blackout_duration": (1, 2),
    },
    "large": {
        "terrain_pool": ["steep", "mixed", "snow"],
        "prescription_pool": ["clearcut", "variable_retention"],
        "crew_pool": ["crew-1", "crew-2", "crew-3", "crew-4"],
        "capability_pool": ["harvester", "forwarder", "processor", "grader"],
        "crew_capability_span": (2, 3),
        "blackout_probability": 0.2,
        "blackout_duration": (2, 3),
    },
}


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
    landing_capacity: tuple[int, int] | int = (1, 3)
    work_required: tuple[float, float] = (6.0, 18.0)
    production_rate: tuple[float, float] = (6.0, 18.0)
    availability_probability: float = 0.9
    blackout_probability: float = 0.1
    blackout_duration: tuple[int, int] | int = (1, 2)
    role_pool: list[str] = field(default_factory=lambda: ["harvester", "forwarder"])
    tier: str | None = None
    terrain_pool: list[str] = field(default_factory=lambda: ["mixed"])
    prescription_pool: list[str] = field(default_factory=lambda: ["clearcut"])
    crew_pool: list[str] = field(default_factory=lambda: ["crew-1", "crew-2"])
    capability_pool: list[str] = field(default_factory=lambda: ["harvester", "forwarder"])
    crew_capability_span: tuple[int, int] = (1, 2)


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
                    key: system.model_dump(exclude_none=True)
                    for key, system in self.scenario.harvest_systems.items()
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
    blackout_probability = tier_defaults.get("blackout_probability", config.blackout_probability)
    blackout_duration = tier_defaults.get("blackout_duration", config.blackout_duration)
    terrain_pool = tier_defaults.get("terrain_pool", config.terrain_pool)
    prescription_pool = tier_defaults.get("prescription_pool", config.prescription_pool)
    crew_pool = tier_defaults.get("crew_pool", config.crew_pool)
    capability_pool = tier_defaults.get("capability_pool", config.capability_pool or config.role_pool)
    crew_capability_span = tier_defaults.get("crew_capability_span", config.crew_capability_span)
    blocks_records: list[dict[str, object]] = []
    for idx in range(num_blocks):
        landing_id = rng.choice(landing_ids)
        work_required = round(_sample_float(rng, config.work_required), 3)
        earliest = rng.randint(1, num_days)
        latest = rng.randint(earliest, num_days)
        terrain = feature_rng.choice(terrain_pool) if terrain_pool else None
        prescription = feature_rng.choice(prescription_pool) if prescription_pool else None
        blocks_records.append(
            {
                "id": f"B{idx + 1}",
                "landing_id": landing_id,
                "work_required": work_required,
                "earliest_start": earliest,
                "latest_finish": latest,
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
        role = role_pool[idx % len(role_pool)] if role_pool else None
        assigned_crew = crew_ids[idx] if crew_ids else None
        machines_records.append(
            {
                "id": f"M{idx + 1}",
                "role": role,
                "crew": assigned_crew,
                "daily_hours": round(_sample_float(rng, config.shift_hours), 2),
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
    for machine in machines_records:
        for day in range(1, num_days + 1):
            available = 1 if rng.random() <= config.availability_probability else 0
            calendar_records.append(
                {
                    "machine_id": machine["id"],
                    "day": day,
                    "available": available,
                }
            )

    production_records: list[dict[str, object]] = []
    for machine in machines_records:
        for block in blocks_records:
            rate = round(_sample_float(rng, config.production_rate), 3)
            production_records.append(
                {
                    "machine_id": machine["id"],
                    "block_id": block["id"],
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
        if rng.random() <= blackout_probability:
            duration = max(1, _sample_int(rng, blackout_duration))
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

    blocks = [Block(**record) for record in blocks_records]
    machines = [Machine(**record) for record in machines_records]
    landings = [Landing(**record) for record in landings_records]
    calendar = [CalendarEntry(**record) for record in calendar_records]
    production_rates = [ProductionRate(**record) for record in production_records]

    crew_assignment_models: list[CrewAssignment] | None = None
    if crew_pool:
        assignments: list[CrewAssignment] = []
        for machine in machines:
            crew_id = machine.crew
            if crew_id is None:
                continue
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
                machine.model_copy(update={"role": roles[idx % len(roles)]})
                for idx, machine in enumerate(scenario.machines)
            ]
            scenario = scenario.model_copy(update={"machines": updated_machines})
        updated_blocks = []
        system_ids = list(systems.keys())
        for idx, block in enumerate(scenario.blocks):
            system_id = system_ids[idx % len(system_ids)]
            updated_blocks.append(block.model_copy(update={"harvest_system_id": system_id}))
        scenario = scenario.model_copy(update={"blocks": updated_blocks, "harvest_systems": systems})

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
        "blackouts": [
            blackout.model_dump(exclude_none=True) for blackout in blackouts
        ],
        "shifts_per_day": config.shifts_per_day,
        "shift_hours": shift_def.hours,
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
    "generate_basic",
    "generate_with_systems",
    "generate_random_dataset",
]
