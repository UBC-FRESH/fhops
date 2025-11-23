"""Pydantic models describing FHOPS scenario inputs."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

from fhops.costing.machine_rates import compose_default_rental_rate_for_role, normalize_machine_role
from fhops.scheduling import MobilisationConfig, TimelineConfig
from fhops.scheduling.systems import HarvestSystem, default_system_registry


class ScheduleLock(BaseModel):
    """Immutable assignment of a machine to a block on a specific day.

    Attributes
    ----------
    machine_id:
        Identifier of the machine being locked (must exist in ``Scenario.machines``).
    block_id:
        Identifier of the block that must be worked during the lock.
    day:
        One-indexed day within the planning horizon where the lock applies.
    """
    machine_id: str
    block_id: str
    day: Day


class ObjectiveWeights(BaseModel):
    """Scalar weights that tune the MIP objective components.

    Attributes
    ----------
    production:
        Multiplier for production (volume/work units). Defaults to 1.0.
    mobilisation:
        Multiplier for mobilisation costs estimated from transition binaries. Defaults to 1.0.
    transitions:
        Optional penalty on the count of machine transitions irrespective of mobilisation spend.
    landing_slack:
        Penalty on soft landing-capacity slack variables when `landing_capacity` is exceeded.
    """

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


class SalvageProcessingMode(str, Enum):
    STANDARD_MILL = "standard_mill"
    PORTABLE_MILL = "portable_mill"
    IN_WOODS_CHIPPING = "in_woods_chipping"


class Block(BaseModel):
    """Harvest block metadata and scheduling window.

    Attributes
    ----------
    id:
        Unique block identifier (referenced by production rates and assignments).
    landing_id:
        Landing where wood is forwarded; constrains landing daily capacity.
    work_required:
        Total work units (machine-hours equivalent) necessary to complete the block.
    earliest_start:
        Optional earliest day (inclusive, 1-indexed) when the block can begin.
    latest_finish:
        Optional latest day (inclusive) when the block must finish.
    harvest_system_id:
        Optional harvest system definition that restricts machine roles per block.
    avg_stem_size_m3 / volume_per_ha_m3 / volume_per_ha_m3_sigma:
        Stand descriptors (cubic metres) surfaced in analytics and productivity lookups.
    stem_density_per_ha / stem_density_per_ha_sigma:
        Stems per hectare statistics used by some productivity models.
    ground_slope_percent:
        Mean slope (%) for the block — used by productivity heuristics and diagnostics.
    salvage_processing_mode:
        Enum describing downstream salvage processing (affects evaluation notes).
    """
    id: str
    landing_id: str
    work_required: float  # in 'work units' (e.g., machine-hours) to complete block
    earliest_start: Day | None = 1
    latest_finish: Day | None = None
    harvest_system_id: str | None = None
    avg_stem_size_m3: float | None = None
    volume_per_ha_m3: float | None = None
    volume_per_ha_m3_sigma: float | None = None
    stem_density_per_ha: float | None = None
    stem_density_per_ha_sigma: float | None = None
    ground_slope_percent: float | None = None
    salvage_processing_mode: SalvageProcessingMode | None = None

    @field_validator("work_required")
    @classmethod
    def _work_positive(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Block.work_required must be non-negative")
        return value

    @field_validator(
        "avg_stem_size_m3",
        "volume_per_ha_m3",
        "volume_per_ha_m3_sigma",
        "stem_density_per_ha",
        "stem_density_per_ha_sigma",
        "ground_slope_percent",
    )
    @classmethod
    def _optional_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Block stand attribute fields must be non-negative")
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
    """Machine definition (identifier, crew, availability, and costing metadata).

    Attributes
    ----------
    id:
        Unique machine identifier referenced throughout calendars/assignments.
    crew:
        Optional crew label for reporting/telemetry grouping.
    daily_hours:
        Maximum hours the machine can operate per day (defaults to 24).
    operating_cost:
        Cost per scheduled machine hour (SMH) expressed in scenario currency units.
    role:
        Optional machine role string (normalised via ``normalize_machine_role``) used by harvest
        systems and rental-rate lookups.
    repair_usage_hours:
        Optional cumulative repair hours that influences the rental-rate defaults.
    """
    id: str
    crew: str | None = None
    daily_hours: float = 24.0
    operating_cost: float = 0.0
    role: str | None = None
    repair_usage_hours: int | None = None

    @field_validator("daily_hours", "operating_cost")
    @classmethod
    def _machine_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Machine numerical fields must be non-negative")
        return value

    @field_validator("repair_usage_hours")
    @classmethod
    def _usage_non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("Machine.repair_usage_hours must be non-negative")
        return value

    @field_validator("role")
    @classmethod
    def _normalise_role(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_machine_role(value)
        return normalized

    @model_validator(mode="after")
    def _apply_role_defaults(self) -> Machine:
        role = self.role
        if (self.operating_cost is None or self.operating_cost <= 0) and role:
            composed = compose_default_rental_rate_for_role(
                role,
                usage_hours=self.repair_usage_hours,
            )
            if composed is not None:
                operating_cost, _ = composed
                object.__setattr__(self, "operating_cost", operating_cost)
        return self


class RoadConstruction(BaseModel):
    """Road/subgrade construction job describing TR-28 soil profiles and costing metadata.

    Attributes
    ----------
    id:
        Unique job identifier referenced in telemetry and costing exports.
    machine_slug:
        Machine rate slug (``tr28`` index) used to determine construction costs.
    road_length_m:
        Length of the road section (metres) to construct.
    include_mobilisation:
        When ``True``, mobilisation costs are included in the estimate.
    soil_profile_ids:
        Optional list of TR-28 soil profile identifiers associated with the job.
    notes:
        Free-form comments surfaced in CLI summaries.
    """
    id: str
    machine_slug: str
    road_length_m: float
    include_mobilisation: bool = True
    soil_profile_ids: list[str] | None = None
    notes: str | None = None

    @field_validator("id", "machine_slug")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("RoadConstruction id/machine_slug must be non-empty")
        return value.strip()

    @field_validator("road_length_m")
    @classmethod
    def _positive_length(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("RoadConstruction.road_length_m must be > 0")
        return value

    @field_validator("soil_profile_ids")
    @classmethod
    def _normalise_profiles(cls, value: list[str] | None) -> list[str] | None:
        if not value:
            return None
        cleaned = [profile.strip() for profile in value if profile and profile.strip()]
        return cleaned or None


class Landing(BaseModel):
    """Landing metadata including per-day assignment capacity.

    Attributes
    ----------
    id:
        Landing identifier referenced by blocks and mobilisation logic.
    daily_capacity:
        Maximum number of machines that can work on the landing concurrently per day.
    """
    id: str
    daily_capacity: int = 2  # max machines concurrently working

    @field_validator("daily_capacity")
    @classmethod
    def _capacity_positive(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Landing.daily_capacity must be non-negative")
        return value


class CalendarEntry(BaseModel):
    """Day-level availability for a machine.

    Attributes
    ----------
    machine_id:
        Identifier of the machine whose availability is being set.
    day:
        One-indexed day number relative to the scenario horizon.
    available:
        Binary flag (1 available, 0 unavailable) controlling day-level assignment eligibility.
    """
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


class ShiftCalendarEntry(BaseModel):
    """Machine availability at the shift granularity.

    Attributes
    ----------
    machine_id:
        Identifier of the machine whose shift availability is being declared.
    day:
        One-indexed day number where the shift entry applies.
    shift_id:
        Shift label (e.g., ``S1``, ``DAYS``, ``NIGHTS``) consistent with ``TimelineConfig``.
    available:
        Binary flag (1 available, 0 unavailable) controlling shift-level assignment eligibility.
    """
    machine_id: str
    day: Day
    shift_id: str
    available: int = 1

    @field_validator("day")
    @classmethod
    def _day_positive(cls, value: Day) -> Day:
        if value < 1:
            raise ValueError("ShiftCalendarEntry.day must be >= 1")
        return value

    @field_validator("shift_id")
    @classmethod
    def _shift_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ShiftCalendarEntry.shift_id must be non-empty")
        return value

    @field_validator("available")
    @classmethod
    def _availability_flag(cls, value: int) -> int:
        if value not in (0, 1):
            raise ValueError("ShiftCalendarEntry.available must be 0 or 1")
        return value


class ProductionRate(BaseModel):
    """Per-day production rate measured in work units for a machine/block pair.

    Attributes
    ----------
    machine_id:
        Machine identifier (must exist in ``Scenario.machines``).
    block_id:
        Block identifier (must exist in ``Scenario.blocks``).
    rate:
        Work units produced per full shift/day assignment. Must be non-negative.
    """
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
    """Top-level container for the FHOPS data contract.

    The model mirrors the CSV/YAML inputs documented in ``docs/howto/data_contract.rst`` and is the
    object returned by :func:`fhops.scenario.io.load_scenario`.  Only validated, horizon-bounded data
    reaches this point, which means downstream solvers (MIP + heuristics) can rely on:

    - every block referencing a known landing/harvest system,
    - machine calendars/shift calendars never exceeding ``num_days``,
    - mobilisation tables referencing existing blocks/machines, and
    - optional extras (crew assignments, road construction, GeoJSON metadata) being present only when
      fully specified.

    Attributes
    ----------
    name:
        Human-readable scenario label surfaced in CLI/Evaluation outputs.
    num_days:
        Planning horizon length (integer number of days).
    schema_version:
        Version of the input schema; used to guard loader compatibility.
    start_date:
        Optional ISO date string used for timestamped exports.
    blocks / machines / landings:
        Validated lists of the corresponding Pydantic models.
    calendar / shift_calendar:
        Availability tables. ``shift_calendar`` may be ``None`` for day-level scenarios.
    production_rates:
        Machine/block productivity table measured in work units per assignment.
    timeline:
        Optional :class:`~fhops.scheduling.timeline.models.TimelineConfig` describing shifts, blackout windows, etc.
    mobilisation:
        Optional :class:`~fhops.scheduling.mobilisation.MobilisationConfig` describing distances and per-machine parameters.
    harvest_systems:
        Optional registry mapping harvest-system IDs to :class:`~fhops.scheduling.systems.HarvestSystem` definitions.
    geo:
        Optional :class:`GeoMetadata` with GeoJSON lookups.
    crew_assignments:
        Optional list mapping crew IDs to machines for reporting/telemetry.
    locked_assignments:
        Optional list of :class:`ScheduleLock` entries that pin machines to blocks on specific days.
    objective_weights:
        Optional :class:`ObjectiveWeights` overriding default solver weights.
    road_construction:
        Optional list of :class:`RoadConstruction` entries used by telemetry/costing exports.

    Notes
    -----
    The helper methods (``machine_ids()``, ``window_for()``, etc.) are convenience routines for the
    solver/evaluation layers and are intentionally lightweight so they can be used in tight loops.
    """
    name: str
    num_days: int
    schema_version: str = "1.0.0"
    start_date: date | None = None  # ISO date for reporting (optional)
    blocks: list[Block]
    machines: list[Machine]
    landings: list[Landing]
    calendar: list[CalendarEntry]
    shift_calendar: list[ShiftCalendarEntry] | None = None
    production_rates: list[ProductionRate]
    timeline: TimelineConfig | None = None
    mobilisation: MobilisationConfig | None = None
    harvest_systems: dict[str, HarvestSystem] | None = None
    geo: GeoMetadata | None = None
    crew_assignments: list[CrewAssignment] | None = None
    locked_assignments: list[ScheduleLock] | None = None
    objective_weights: ObjectiveWeights | None = None
    road_construction: list[RoadConstruction] | None = None

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
        """Return the list of machine identifiers defined in the scenario."""
        return [machine.id for machine in self.machines]

    def block_ids(self) -> list[str]:
        """Return the list of block identifiers defined in the scenario."""
        return [block.id for block in self.blocks]

    def landing_ids(self) -> list[str]:
        """Return the list of landing identifiers defined in the scenario."""
        return [landing.id for landing in self.landings]

    def window_for(self, block_id: str) -> tuple[int, int]:
        """Return the inclusive (earliest, latest) day window for the target block."""
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

        if self.shift_calendar:
            for shift_entry in self.shift_calendar:
                if shift_entry.machine_id not in machine_ids:
                    raise ValueError(
                        f"Shift calendar entry references unknown machine_id={shift_entry.machine_id}"
                    )
                if shift_entry.day > self.num_days:
                    raise ValueError(
                        f"Shift calendar entry day {shift_entry.day} exceeds scenario horizon num_days={self.num_days}"
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
        if self.road_construction:
            seen_jobs: set[str] = set()
            for entry in self.road_construction:
                if entry.id in seen_jobs:
                    raise ValueError(
                        f"Duplicate road_construction id '{entry.id}'. IDs must be unique."
                    )
                seen_jobs.add(entry.id)

        return self


class ShiftInstance(BaseModel):
    """Concrete shift slot identified by day and shift label.

    Attributes
    ----------
    day:
        One-indexed day number for the shift.
    shift_id:
        Shift label (string) matching the scenario's shift definitions.
    """
    day: Day
    shift_id: str

    @field_validator("shift_id")
    @classmethod
    def _shift_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ShiftInstance.shift_id must be non-empty")
        return value


class Problem(BaseModel):
    """Runtime representation of a scenario used by solvers.

    ``Problem`` wraps a validated :class:`Scenario` and expands it into concrete ``days`` and
    ``shifts`` so optimisation code can iterate over deterministic index sets without repeatedly
    querying the Scenario.  ``Problem.from_scenario`` is the canonical constructor; it injects the
    default harvest-system registry (when necessary) and synthesises single-shift calendars for
    legacy day-indexed inputs.

    Attributes
    ----------
    scenario:
        Back-reference to the source :class:`Scenario`.
    days:
        List of integer day indices derived from ``scenario.num_days``.
    shifts:
        List of :class:`ShiftInstance` entries representing every (day, shift_id) slot the solver
        should consider.

    Notes
    -----
    Any code that builds Pyomo models or heuristic plans should accept a ``Problem`` rather than the
    raw ``Scenario`` to avoid recomputing shift/day metadata.
    """
    scenario: Scenario
    days: list[Day]
    shifts: list[ShiftInstance]

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> Problem:
        if scenario.harvest_systems is None:
            scenario = scenario.model_copy(
                update={"harvest_systems": dict(default_system_registry())}
            )
        days = list(range(1, scenario.num_days + 1))
        shifts: list[ShiftInstance]
        if scenario.shift_calendar:
            unique = {
                (entry.day, entry.shift_id)
                for entry in scenario.shift_calendar
                if entry.available == 1
            }
            shifts = [ShiftInstance(day=day, shift_id=shift_id) for day, shift_id in sorted(unique)]
        elif scenario.timeline and scenario.timeline.shifts:
            shifts = []
            for day in days:
                for shift_def in scenario.timeline.shifts:
                    shifts.append(ShiftInstance(day=day, shift_id=shift_def.name))
        else:
            shifts = [ShiftInstance(day=day, shift_id="S1") for day in days]
        return cls(scenario=scenario, days=days, shifts=shifts)


__all__ = [
    "Day",
    "Block",
    "Machine",
    "RoadConstruction",
    "Landing",
    "CalendarEntry",
    "ShiftCalendarEntry",
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
    "ShiftInstance",
]


class GeoMetadata(BaseModel):
    """Optional geospatial metadata references associated with a scenario.

    Attributes
    ----------
    block_geojson:
        Relative path to a GeoJSON FeatureCollection describing block polygons.
    landing_geojson:
        Relative path to a GeoJSON FeatureCollection describing landing/road locations.
    crs:
        Coordinate reference system string (e.g., ``EPSG:3005``) used when plotting.
    notes:
        Free-form remarks shown in CLI inspectors and docs.
    """
    block_geojson: str | None = None
    landing_geojson: str | None = None
    crs: str | None = None
    notes: str | None = None


class CrewAssignment(BaseModel):
    """Optional mapping of crews to machines/roles.

    Attributes
    ----------
    crew_id:
        Unique crew identifier.
    machine_id:
        Machine assigned to the crew.
    primary_role:
        Optional role label associated with the crew (e.g., fallers, processors).
    notes:
        Additional metadata surfaced in telemetry exports.
    """
    crew_id: str
    machine_id: str
    primary_role: str | None = None
    notes: str | None = None
