"""Synthetic scenario generator scaffolding."""

from __future__ import annotations

from dataclasses import dataclass

from fhops.scenario.contract import Block, CalendarEntry, Landing, Machine, ProductionRate, Scenario


@dataclass
class SyntheticScenarioSpec:
    """Configuration for generating synthetic scenarios."""

    num_blocks: int
    num_days: int
    num_machines: int
    landing_capacity: int = 1


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
    return Scenario(
        name="synthetic-basic",
        num_days=spec.num_days,
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        production_rates=production_rates,
    )


__all__ = ["SyntheticScenarioSpec", "generate_basic"]
