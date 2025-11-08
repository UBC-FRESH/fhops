"""Synthetic scenario generator scaffolding."""

from __future__ import annotations

from dataclasses import dataclass

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


__all__ = ["SyntheticScenarioSpec", "generate_basic", "generate_with_systems"]
