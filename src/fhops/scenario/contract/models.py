"""Pydantic models describing FHOPS scenario inputs."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

from fhops.scheduling import MobilisationConfig, TimelineConfig
from fhops.scheduling.systems import HarvestSystem, default_system_registry


class ScheduleLock(BaseModel):
    machine_id: str
    block_id: str
    day: Day


class ObjectiveWeights(BaseModel):
    production: float = 1.0
    mobilisation: float = 1.0
    transitions: float = 0.0
    landing_slack: float = 0.0

    @field_validator("production", "mobilisation", "transitions", "landing_slack")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Objective weight components must be non-negative")
        return value


Day = int  # 1..D


class Block(BaseModel):
    """Harvest block metadata and scheduling window."""

    id: str
    landing_id: str
    work_required: float  # in 'work units' (e.g., machine-hours) to complete block
    earliest_start: Day | None = 1
    latest_finish: Day | None = None
    harvest_system_id: str | None = None

    @field_validator("work_required")
    @classmethod
    def _work_positive(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Block.work_required must be non-negative")
        return value

    @field_validator("earliest_start")
    @classmethod
    def _earliest_positive(cls, value: Day | None) -> Day | None:
        if value is not None and value < 1:
            raise ValueError("Block.earliest_start must be >= 1")
        return value

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

    @field_validator("daily_hours", "operating_cost")
    @classmethod
    def _machine_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Machine numerical fields must be non-negative")
        return value


class Landing(BaseModel):
    id: str
    daily_capacity: int = 2  # max machines concurrently working

    @field_validator("daily_capacity")
    @classmethod
    def _capacity_positive(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Landing.daily_capacity must be non-negative")
        return value


class CalendarEntry(BaseModel):
    machine_id: str
    day: Day
    available: int = 1  # 1 available, 0 not available

    @field_validator("day")
    @classmethod
    def _day_positive(cls, value: Day) -> Day:
        if value < 1:
            raise ValueError("CalendarEntry.day must be >= 1")
        return value

    @field_validator("available")
    @classmethod
    def _availability_flag(cls, value: int) -> int:
        if value not in (0, 1):
            raise ValueError("CalendarEntry.available must be 0 or 1")
        return value


class ProductionRate(BaseModel):
    machine_id: str
    block_id: str
    rate: float  # work units per day if assigned (<= work_required/block)

    @field_validator("rate")
    @classmethod
    def _rate_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("ProductionRate.rate must be non-negative")
        return value


class Scenario(BaseModel):
    name: str
    num_days: int
    schema_version: str = "1.0.0"
    start_date: date | None = None  # ISO date for reporting (optional)
    blocks: list[Block]
    machines: list[Machine]
    landings: list[Landing]
    calendar: list[CalendarEntry]
    production_rates: list[ProductionRate]
    timeline: TimelineConfig | None = None
    mobilisation: MobilisationConfig | None = None
    harvest_systems: dict[str, HarvestSystem] | None = None
    geo: GeoMetadata | None = None
    crew_assignments: list[CrewAssignment] | None = None
    locked_assignments: list[ScheduleLock] | None = None
    objective_weights: ObjectiveWeights | None = None

    @field_validator("num_days")
    @classmethod
    def _num_days_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Scenario.num_days must be >= 1")
        return value

    @field_validator("schema_version")
    @classmethod
    def _schema_version_supported(cls, value: str) -> str:
        supported = {"1.0.0"}
        if value not in supported:
            raise ValueError(
                f"Unsupported schema_version={value}. Supported versions: {', '.join(sorted(supported))}"
            )
        return value

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

    @model_validator(mode="after")
    def _cross_validate(self) -> Scenario:
        block_ids = {block.id for block in self.blocks}
        landing_ids = {landing.id for landing in self.landings}
        machine_ids = {machine.id for machine in self.machines}

        for block in self.blocks:
            if block.landing_id not in landing_ids:
                raise ValueError(
                    f"Block {block.id} references unknown landing_id={block.landing_id}"
                )
            if block.earliest_start is not None and block.earliest_start > self.num_days:
                raise ValueError(
                    f"Block {block.id} earliest_start exceeds num_days={self.num_days}"
                )
            if block.latest_finish is not None and block.latest_finish > self.num_days:
                raise ValueError(f"Block {block.id} latest_finish exceeds num_days={self.num_days}")

        for entry in self.calendar:
            if entry.machine_id not in machine_ids:
                raise ValueError(f"Calendar entry references unknown machine_id={entry.machine_id}")
            if entry.day > self.num_days:
                raise ValueError(
                    f"Calendar entry day {entry.day} exceeds scenario horizon num_days={self.num_days}"
                )

        for rate in self.production_rates:
            if rate.machine_id not in machine_ids:
                raise ValueError(f"Production rate references unknown machine_id={rate.machine_id}")
            if rate.block_id not in block_ids:
                raise ValueError(f"Production rate references unknown block_id={rate.block_id}")

        mobilisation = self.mobilisation
        if mobilisation and mobilisation.distances:
            for dist in mobilisation.distances:
                if dist.from_block not in block_ids or dist.to_block not in block_ids:
                    raise ValueError(
                        "Mobilisation distance references unknown block_id "
                        f"{dist.from_block}->{dist.to_block}"
                    )
        if mobilisation and mobilisation.machine_params:
            for param in mobilisation.machine_params:
                if param.machine_id not in machine_ids:
                    raise ValueError(
                        f"Mobilisation config references unknown machine_id={param.machine_id}"
                    )

        if self.crew_assignments:
            seen_crews: set[str] = set()
            for assignment in self.crew_assignments:
                if assignment.machine_id not in machine_ids:
                    raise ValueError(
                        f"Crew assignment references unknown machine_id={assignment.machine_id}"
                    )
                if assignment.crew_id in seen_crews:
                    raise ValueError(f"Duplicate crew_id in assignments: {assignment.crew_id}")
                seen_crews.add(assignment.crew_id)

        if self.locked_assignments:
            seen_locks: set[tuple[str, int]] = set()
            for lock in self.locked_assignments:
                if lock.machine_id not in machine_ids:
                    raise ValueError(
                        f"Locked assignment references unknown machine_id={lock.machine_id}"
                    )
                if lock.block_id not in block_ids:
                    raise ValueError(
                        f"Locked assignment references unknown block_id={lock.block_id}"
                    )
                if lock.day < 1 or lock.day > self.num_days:
                    raise ValueError(f"Locked assignment day {lock.day} outside scenario horizon")
                key = (lock.machine_id, lock.day)
                if key in seen_locks:
                    raise ValueError(
                        f"Multiple locked assignments for machine {lock.machine_id} on day {lock.day}"
                    )
                seen_locks.add(key)
            if self.timeline and self.timeline.blackouts:
                for lock in self.locked_assignments:
                    for blackout in self.timeline.blackouts:
                        if blackout.start_day <= lock.day <= blackout.end_day:
                            raise ValueError(
                                f"Locked assignment for machine {lock.machine_id} falls within blackout"
                            )

        return self


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
    "GeoMetadata",
    "CrewAssignment",
    "ScheduleLock",
    "ObjectiveWeights",
]


class GeoMetadata(BaseModel):
    """Optional geospatial metadata locations and metadata."""

    block_geojson: str | None = None
    landing_geojson: str | None = None
    crs: str | None = None
    notes: str | None = None


class CrewAssignment(BaseModel):
    """Optional mapping of crews to machines/roles."""

    crew_id: str
    machine_id: str
    primary_role: str | None = None
    notes: str | None = None
