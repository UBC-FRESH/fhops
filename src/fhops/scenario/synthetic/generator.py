"""Synthetic scenario generator scaffolding."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scheduling.systems import HarvestSystem, default_system_registry
from fhops.scheduling.timeline import BlackoutWindow, ShiftDefinition, TimelineConfig


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


@dataclass
class SyntheticDatasetBundle:
    """Container for generated scenario tables and helpers to persist them."""

    scenario: Scenario
    blocks: pd.DataFrame
    machines: pd.DataFrame
    landings: pd.DataFrame
    calendar: pd.DataFrame
    production_rates: pd.DataFrame

    def write(self, out_dir: Path, *, include_yaml: bool = True) -> Path:
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
            payload: dict[str, object] = {
                "name": self.scenario.name,
                "num_days": self.scenario.num_days,
                "schema_version": self.scenario.schema_version,
                "data": {
                    "blocks": "data/blocks.csv",
                    "machines": "data/machines.csv",
                    "landings": "data/landings.csv",
                    "calendar": "data/calendar.csv",
                    "prod_rates": "data/prod_rates.csv",
                },
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
    num_blocks = _sample_int(rng, config.num_blocks)
    num_days = _sample_int(rng, config.num_days)
    num_machines = _sample_int(rng, config.num_machines)
    num_landings = max(1, _sample_int(rng, config.num_landings))

    landing_ids = [f"L{i + 1}" for i in range(num_landings)]
    blocks_records: list[dict[str, object]] = []
    for idx in range(num_blocks):
        landing_id = rng.choice(landing_ids)
        work_required = round(_sample_float(rng, config.work_required), 3)
        earliest = rng.randint(1, num_days)
        latest = rng.randint(earliest, num_days)
        blocks_records.append(
            {
                "id": f"B{idx + 1}",
                "landing_id": landing_id,
                "work_required": work_required,
                "earliest_start": earliest,
                "latest_finish": latest,
            }
        )

    role_pool = config.role_pool or []
    machines_records: list[dict[str, object]] = []
    for idx in range(num_machines):
        role = role_pool[idx % len(role_pool)] if role_pool else None
        machines_records.append(
            {
                "id": f"M{idx + 1}",
                "role": role,
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
    for day in range(1, num_days + 1):
        if rng.random() <= config.blackout_probability:
            duration = max(1, _sample_int(rng, config.blackout_duration))
            blackouts.append(
                BlackoutWindow(
                    start_day=day,
                    end_day=min(num_days, day + duration - 1),
                    reason="synthetic-blackout",
                )
            )
    timeline = TimelineConfig(shifts=[shift_def], blackouts=blackouts)

    blocks = [Block(**record) for record in blocks_records]
    machines = [Machine(**record) for record in machines_records]
    landings = [Landing(**record) for record in landings_records]
    calendar = [CalendarEntry(**record) for record in calendar_records]
    production_rates = [ProductionRate(**record) for record in production_records]

    scenario = Scenario(
        name=config.name,
        num_days=num_days,
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        production_rates=production_rates,
        timeline=timeline,
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

    return SyntheticDatasetBundle(
        scenario=scenario,
        blocks=pd.DataFrame.from_records(blocks_records),
        machines=pd.DataFrame.from_records(machines_records),
        landings=pd.DataFrame.from_records(landings_records),
        calendar=pd.DataFrame.from_records(calendar_records),
        production_rates=pd.DataFrame.from_records(production_records),
    )


__all__ = [
    "SyntheticScenarioSpec",
    "SyntheticDatasetConfig",
    "SyntheticDatasetBundle",
    "generate_basic",
    "generate_with_systems",
    "generate_random_dataset",
]
