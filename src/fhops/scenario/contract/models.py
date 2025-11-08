"""Pydantic models describing FHOPS scenario inputs."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ValidationInfo, field_validator

from fhops.scheduling import MobilisationConfig, TimelineConfig
from fhops.scheduling.systems import HarvestSystem, default_system_registry

Day = int  # 1..D


class Block(BaseModel):
    """Harvest block metadata and scheduling window."""

    id: str
    landing_id: str
    work_required: float  # in 'work units' (e.g., machine-hours) to complete block
    earliest_start: Day | None = 1
    latest_finish: Day | None = None
    harvest_system_id: str | None = None

    @field_validator("latest_finish")
    @classmethod
    def _latest_not_before_earliest(cls, value: Day | None, info: ValidationInfo) -> Day | None:
        es = info.data.get("earliest_start", 1)
        if value is not None and value < es:
            raise ValueError("latest_finish must be >= earliest_start")
        return value


class Machine(BaseModel):
    id: str
    crew: str | None = None
    daily_hours: float = 10.0
    operating_cost: float = 0.0
    role: str | None = None


class Landing(BaseModel):
    id: str
    daily_capacity: int = 2  # max machines concurrently working


class CalendarEntry(BaseModel):
    machine_id: str
    day: Day
    available: int = 1  # 1 available, 0 not available


class ProductionRate(BaseModel):
    machine_id: str
    block_id: str
    rate: float  # work units per day if assigned (<= work_required/block)


class Scenario(BaseModel):
    name: str
    num_days: int
    start_date: date | None = None  # ISO date for reporting (optional)
    blocks: list[Block]
    machines: list[Machine]
    landings: list[Landing]
    calendar: list[CalendarEntry]
    production_rates: list[ProductionRate]
    timeline: TimelineConfig | None = None
    mobilisation: MobilisationConfig | None = None
    harvest_systems: dict[str, HarvestSystem] | None = None

    def machine_ids(self) -> list[str]:
        return [machine.id for machine in self.machines]

    def block_ids(self) -> list[str]:
        return [block.id for block in self.blocks]

    def landing_ids(self) -> list[str]:
        return [landing.id for landing in self.landings]

    def window_for(self, block_id: str) -> tuple[int, int]:
        block = next(b for b in self.blocks if b.id == block_id)
        earliest = block.earliest_start if block.earliest_start is not None else 1
        latest = block.latest_finish if block.latest_finish is not None else self.num_days
        return earliest, latest

    @field_validator("blocks")
    @classmethod
    def _validate_system_ids(cls, value: list[Block], info: ValidationInfo) -> list[Block]:
        systems: dict[str, HarvestSystem] | None = info.data.get("harvest_systems")
        if systems:
            known = set(systems.keys())
            for block in value:
                if block.harvest_system_id and block.harvest_system_id not in known:
                    raise ValueError(
                        f"Block {block.id} references unknown harvest_system_id="
                        f"{block.harvest_system_id}"
                    )
        return value


class Problem(BaseModel):
    scenario: Scenario
    days: list[Day]

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> Problem:
        if scenario.harvest_systems is None:
            scenario = scenario.model_copy(
                update={"harvest_systems": dict(default_system_registry())}
            )
        return cls(scenario=scenario, days=list(range(1, scenario.num_days + 1)))


__all__ = [
    "Day",
    "Block",
    "Machine",
    "Landing",
    "CalendarEntry",
    "ProductionRate",
    "Scenario",
    "Problem",
    "TimelineConfig",
    "MobilisationConfig",
    "HarvestSystem",
]
