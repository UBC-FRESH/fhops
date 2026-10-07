"""Pydantic models describing FHOPS scenario inputs."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import cast

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from fhops.costing.machine_rates import compose_default_rental_rate_for_role, normalize_machine_role
from fhops.scheduling import MobilisationConfig, TimelineConfig
from fhops.scheduling.systems import HarvestSystem, default_system_registry


class ScheduleLock(BaseModel):
    """Immutable assignment of a machine to a block on a specific day (or day/shift slot).

    Attributes
    ----------
    machine_id:
        Identifier of the machine being locked (must exist in ``Scenario.machines``).
    block_id:
        Identifier of the block that must be worked during the lock.
    day:
        One-indexed day within the planning horizon where the lock applies.
    shift_id:
        Optional shift label. ``None`` (default) locks every available shift of ``day`` to
        ``block_id`` (the v1.0.0 behaviour). When set, only the ``(day, shift_id)`` slot is locked;
        the label must belong to the scenario's shift grid (``shift_calendar`` labels, timeline
        shift names, or ``S1`` for day-indexed scenarios).
    production:
        Optional planned production (m³, ``>= 0``) of the locked slot. Solvers ignore it; it is
        used when a lock table is *replayed* (rolling-horizon carry-forward and
        :func:`fhops.planning.compute_rolling_kpis`), so a stitched operational-MILP plan is
        evaluated with the production the MILP planned rather than the full production rate.
        ``None`` (default) replays with ``min(rate, remaining)``.

    Notes
    -----
    A day-level lock and a shift-level lock for the same machine/day are rejected by
    :class:`Scenario` validation, as are duplicate ``(machine_id, day, shift_id)`` entries.
    """

    machine_id: str
    block_id: str
    day: Day
    shift_id: str | None = None
    production: float | None = None

    @field_validator("production")
    @classmethod
    def _production_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("ScheduleLock.production must be >= 0")
        return value

    @field_validator("shift_id")
    @classmethod
    def _shift_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("ScheduleLock.shift_id must be non-empty when provided")
        return stripped


class ObjectiveWeights(BaseModel):
    """Scalar weights that tune the MIP objective components.

    Attributes
    ----------
    production:
        Multiplier for production (delivered volume, m³). Defaults to 1.0.
    mobilisation:
        Multiplier for mobilisation costs estimated from transition binaries. Defaults to 1.0.
    transitions:
        Optional penalty on the count of machine transitions irrespective of mobilisation spend.
    landing_surplus:
        Weight of landing-capacity overloads. 0 (default) makes ``Landing.daily_capacity`` a hard
        per-shift-slot limit; a positive weight allows overloads, the ``k``-th machine beyond
        capacity in a slot costing ``k × landing_surplus`` (heuristics and operational MILP).
    """

    production: float = 1.0
    mobilisation: float = 1.0
    transitions: float = 0.0
    landing_surplus: float = 0.0

    @field_validator("production", "mobilisation", "transitions", "landing_surplus")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Objective weight components must be non-negative")
        return value


Day = int  # 1..D


class SalvageProcessingMode(StrEnum):
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
        Volume (m³) that must be delivered from the block to complete it — the terminal
        (e.g., loader) output measured in the same units as ``ProductionRate.rate``. Every role
        of an explicit harvest system processes up to this volume; loader truckload batching,
        playback production, KPIs (``total_production``, ``remaining_work_total``) and all
        reference datasets treat it as m³. Must be non-negative.
    earliest_start:
        Optional earliest day (inclusive, 1-indexed) when the block can begin.
    latest_finish:
        Optional latest day (inclusive) when the block must finish.
    harvest_system_id:
        Optional harvest system definition that restricts machine roles per block. Scenario
        validation requires the id to be a key of ``Scenario.harvest_systems`` or of
        :func:`fhops.scheduling.systems.default_system_registry`.
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
    work_required: float  # terminal delivered volume (m³) required to complete the block
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
    """Landing metadata including its machine capacity.

    Attributes
    ----------
    id:
        Landing identifier referenced by blocks and mobilisation logic.
    daily_capacity:
        Maximum number of machines that can work the landing's blocks concurrently, counted per
        shift slot ``(day, shift_id)`` (on single-shift scenarios: per day). The name is kept for
        compatibility. The heuristics and the operational MILP apply the same rule: when
        ``ObjectiveWeights.landing_surplus`` is 0 (default) the capacity is hard (heuristics:
        the repair keeps landings within capacity and any remaining extra machine costs the hard
        violation penalty, at least 1000, #140; MILP: constraint), otherwise each slot's ``k``-th
        machine beyond capacity costs ``k × landing_surplus``. Before FHOPS 1.0.1 the operational
        MILP counted machine-shifts per day with a slack that was free at weight 0 (#125).
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
    """Production rate (m³ per assignment) for a machine/block pair.

    Attributes
    ----------
    machine_id:
        Machine identifier (must exist in ``Scenario.machines``).
    block_id:
        Block identifier (must exist in ``Scenario.blocks``).
    rate:
        Volume (m³) produced per full shift assignment (per day in single-shift scenarios),
        in the same units as ``Block.work_required``. Must be non-negative.
    """

    machine_id: str
    block_id: str
    rate: float  # m³ per shift assignment (same units as Block.work_required)

    @field_validator("rate")
    @classmethod
    def _rate_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("ProductionRate.rate must be non-negative")
        return value


def _normalise_role_mapping(
    mapping: dict[str, float] | dict[str, int], field_name: str
) -> dict[str, float] | dict[str, int]:
    """Normalise role keys and reject negative values or duplicate normalised keys."""

    normalised: dict = {}
    for raw_role, value in mapping.items():
        role = normalize_machine_role(raw_role)
        if role is None:
            raise ValueError(f"BlockInitialState.{field_name} contains a blank role key")
        if value < 0:
            raise ValueError(
                f"BlockInitialState.{field_name}[{raw_role!r}] must be non-negative (got {value})"
            )
        if role in normalised:
            raise ValueError(
                f"BlockInitialState.{field_name} lists role {role!r} more than once "
                "(after role-name normalisation)"
            )
        normalised[role] = value
    return normalised


class BlockInitialState(BaseModel):
    """Carried-over sequencing state for one block at the start of the horizon.

    Used to resume planning mid-operation (e.g. a rolling-horizon window that starts after some
    volume has already been felled, extracted, or processed). The *terminal* volume still to be
    delivered is expressed through ``Block.work_required`` itself; this model captures the
    intermediate (non-terminal) state of the harvest-system roles.

    Attributes
    ----------
    block_id:
        Identifier of a block in ``Scenario.blocks``.
    role_remaining:
        Mapping ``role -> volume`` (m³) the role may still output on this block, i.e.
        ``work_required`` at the original start minus the role's cumulative output. Roles omitted
        here default to the block's ``work_required`` (the v1.0.0 initialisation). Values must be
        non-negative.
    staged_inventory:
        Mapping ``role -> volume`` (m³) output by that role on this block but not yet consumed by
        its downstream role(s) (for example, felled-but-unskidded wood is keyed by the felling
        role). A downstream role ``r`` starts with ``min`` over its upstream roles' staged volume
        available as input. Roles omitted here start with zero staged volume. Values must be
        non-negative.
    role_shift_counts:
        Mapping ``role -> shifts`` already worked on this block. Informational: it seeds
        :attr:`fhops.evaluation.sequencing.SequencingTracker.role_counts_total` (reported by the
        rolling-horizon carry-forward) but no longer affects sequencing checks, because head-start
        buffers (``role_headstart_shifts``) are enforced as staged upstream volume
        (``staged_inventory``) in the MILP, the heuristics, and playback alike (#109). Roles
        omitted here start at zero. Values must be non-negative integers.

    Notes
    -----
    Role keys are normalised with :func:`fhops.costing.machine_rates.normalize_machine_role`
    (case-insensitive, punctuation → ``_``), so ``"Feller-Buncher"`` becomes ``feller_buncher``.
    Scenario-level validation requires every role key to be a role of the block's harvest system,
    which means the block must declare ``harvest_system_id`` when any role-keyed state is given.
    """

    block_id: str
    role_remaining: dict[str, float] = Field(default_factory=dict)
    staged_inventory: dict[str, float] = Field(default_factory=dict)
    role_shift_counts: dict[str, int] = Field(default_factory=dict)

    @field_validator("role_remaining", "staged_inventory")
    @classmethod
    def _volumes_valid(cls, value: dict[str, float], info: ValidationInfo) -> dict[str, float]:
        return cast(dict[str, float], _normalise_role_mapping(value, str(info.field_name)))

    @field_validator("role_shift_counts")
    @classmethod
    def _counts_valid(cls, value: dict[str, int], info: ValidationInfo) -> dict[str, int]:
        return cast(dict[str, int], _normalise_role_mapping(value, str(info.field_name)))


class MachineInitialState(BaseModel):
    """Carried-over position of one machine at the start of the horizon.

    Attributes
    ----------
    machine_id:
        Identifier of a machine in ``Scenario.machines``.
    last_block_id:
        Block the machine occupied in its last worked slot before the horizon, or ``None`` when
        unknown (the v1.0.0 behaviour: the first move is free). When set, the machine's first
        assignment to a different block is charged mobilisation (``MobilisationConfig``) and a
        transition by the operational MILP, the heuristics, and playback.
    """

    machine_id: str
    last_block_id: str | None = None


class ScenarioInitialState(BaseModel):
    """Optional initial state for a scenario (resume planning mid-operation).

    When ``Scenario.initial_state`` is ``None`` (default) the horizon starts from the FHOPS 1.0.0
    initial conditions: staged inventories and role shift counts start at zero, each role may
    output the full ``work_required``, and machines have no prior position (their first move is
    free). Solver and playback results can still differ from 1.0.0 because of other 1.0.1 fixes
    (MILP/playback sequencing alignment, MILP blackouts, stochastic playback events; see
    ``docs/releases/v1.0.1.md``).

    Scenario files that contain ``initial_state`` require ``fhops>=1.0.1``: FHOPS 1.0.0 silently
    ignores the section (``schema_version`` is unchanged at ``1.0.0``).

    Attributes
    ----------
    blocks:
        Per-block :class:`BlockInitialState` entries (at most one per ``block_id``). Blocks not
        listed start from the default (empty) state.
    machines:
        Per-machine :class:`MachineInitialState` entries (at most one per ``machine_id``).

    Examples
    --------
    >>> state = ScenarioInitialState(
    ...     blocks=[
    ...         BlockInitialState(
    ...             block_id="B01",
    ...             role_remaining={"feller_buncher": 0.0},
    ...             staged_inventory={"feller_buncher": 120.0},
    ...         )
    ...     ],
    ...     machines=[MachineInitialState(machine_id="H3", last_block_id="B02")],
    ... )
    >>> state.block_state("B01").staged_inventory
    {'feller_buncher': 120.0}
    """

    blocks: list[BlockInitialState] = Field(default_factory=list)
    machines: list[MachineInitialState] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> ScenarioInitialState:
        seen_blocks: set[str] = set()
        for block_state in self.blocks:
            if block_state.block_id in seen_blocks:
                raise ValueError(
                    f"initial_state lists block_id={block_state.block_id} more than once"
                )
            seen_blocks.add(block_state.block_id)
        seen_machines: set[str] = set()
        for machine_state in self.machines:
            if machine_state.machine_id in seen_machines:
                raise ValueError(
                    f"initial_state lists machine_id={machine_state.machine_id} more than once"
                )
            seen_machines.add(machine_state.machine_id)
        return self

    def block_state(self, block_id: str) -> BlockInitialState | None:
        """Return the :class:`BlockInitialState` for ``block_id`` (``None`` when absent)."""
        return next((state for state in self.blocks if state.block_id == block_id), None)

    def last_block_by_machine(self) -> dict[str, str]:
        """Return ``machine_id -> last_block_id`` for machines with a known prior position."""
        return {
            state.machine_id: state.last_block_id
            for state in self.machines
            if state.last_block_id is not None
        }


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
        Machine/block productivity table measured in m³ per shift assignment.
    timeline:
        Optional :class:`~fhops.scheduling.timeline.models.TimelineConfig` describing shifts, blackout windows, etc.
    mobilisation:
        Optional :class:`~fhops.scheduling.mobilisation.MobilisationConfig` describing distances and per-machine parameters.
    harvest_systems:
        Optional registry mapping harvest-system IDs to :class:`~fhops.scheduling.systems.HarvestSystem` definitions.
        Entries are overlaid on :func:`fhops.scheduling.systems.default_system_registry`; every
        ``Block.harvest_system_id`` must name a system of that combined registry (unknown ids are
        rejected since 1.0.1; 1.0.0 accepted them).
    geo:
        Optional :class:`GeoMetadata` with GeoJSON lookups.
    crew_assignments:
        Optional list mapping crew IDs to machines for reporting/telemetry.
    locked_assignments:
        Optional list of :class:`ScheduleLock` entries that pin machines to blocks on specific days
        (or specific day/shift slots when ``ScheduleLock.shift_id`` is set). Enforced by the
        operational MILP, the legacy MIP builder, and the heuristics. Validation rejects unknown
        machine/block ids, days outside the horizon or the block's
        ``[earliest_start, latest_finish]`` window, blackout days, unknown shift labels (see
        :meth:`shift_labels`), duplicate or mixed day/shift locks, and machines whose role is not
        a role of the block's explicit harvest system. Files using ``shift_id`` require
        ``fhops>=1.0.1`` (1.0.0 reads such entries as whole-day locks).
    objective_weights:
        Optional :class:`ObjectiveWeights` overriding default solver weights.
    road_construction:
        Optional list of :class:`RoadConstruction` entries used by telemetry/costing exports.
    initial_state:
        Optional :class:`ScenarioInitialState` carrying staged inter-role inventory, remaining
        per-role output, head-start shift counts, and each machine's last block at the start of
        the horizon. ``None`` (default) starts from the 1.0.0 initial conditions (empty staged
        inventory, full ``work_required`` per role, no prior machine position); it does not undo
        other 1.0.1 behaviour changes. Validation requires known block/machine ids, non-negative
        values, role keys drawn from the block's harvest-system roles, ``role_remaining`` values
        not above the block's ``work_required``, and ``last_block_id`` values that are scenario
        blocks. Files using this field require ``fhops>=1.0.1`` (1.0.0 ignores it).

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
    initial_state: ScenarioInitialState | None = None

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

    @model_validator(mode="after")
    def _cross_validate(self) -> Scenario:
        block_ids = {block.id for block in self.blocks}
        landing_ids = {landing.id for landing in self.landings}
        machine_ids = {machine.id for machine in self.machines}
        known_system_ids: set[str] | None = None

        for block in self.blocks:
            if block.landing_id not in landing_ids:
                raise ValueError(
                    f"Block {block.id} references unknown landing_id={block.landing_id}"
                )
            if block.harvest_system_id:
                if known_system_ids is None:
                    known_system_ids = set(_harvest_system_registry(self))
                if block.harvest_system_id not in known_system_ids:
                    raise ValueError(
                        f"Block {block.id} references unknown harvest_system_id="
                        f"{block.harvest_system_id}; define it under harvest_systems or use a "
                        "system from fhops.scheduling.systems.default_system_registry()"
                    )
            if block.earliest_start is not None and block.earliest_start > self.num_days:
                raise ValueError(
                    f"Block {block.id} earliest_start exceeds num_days={self.num_days}"
                )
            if block.latest_finish is not None and block.latest_finish > self.num_days:
                raise ValueError(f"Block {block.id} latest_finish exceeds num_days={self.num_days}")

        for calendar_entry in self.calendar:
            if calendar_entry.machine_id not in machine_ids:
                raise ValueError(
                    f"Calendar entry references unknown machine_id={calendar_entry.machine_id}"
                )
            if calendar_entry.day > self.num_days:
                raise ValueError(
                    "Calendar entry day "
                    f"{calendar_entry.day} exceeds scenario horizon num_days={self.num_days}"
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
            day_locks: set[tuple[str, int]] = set()
            shift_locks: set[tuple[str, int, str]] = set()
            shift_locked_days: set[tuple[str, int]] = set()
            known_shift_ids = self.shift_labels()
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
                if lock.shift_id is None:
                    if key in day_locks or key in shift_locked_days:
                        raise ValueError(
                            f"Multiple locked assignments for machine {lock.machine_id} on day {lock.day}"
                        )
                    day_locks.add(key)
                    continue
                if lock.shift_id not in known_shift_ids:
                    raise ValueError(
                        f"Locked assignment for machine {lock.machine_id} references unknown "
                        f"shift_id={lock.shift_id} (known: {', '.join(sorted(known_shift_ids))})"
                    )
                shift_key = (lock.machine_id, lock.day, lock.shift_id)
                if key in day_locks or shift_key in shift_locks:
                    raise ValueError(
                        f"Multiple locked assignments for machine {lock.machine_id} on day "
                        f"{lock.day} shift {lock.shift_id}"
                    )
                shift_locks.add(shift_key)
                shift_locked_days.add(key)
            if self.timeline and self.timeline.blackouts:
                for lock in self.locked_assignments:
                    for blackout in self.timeline.blackouts:
                        if blackout.start_day <= lock.day <= blackout.end_day:
                            raise ValueError(
                                f"Locked assignment for machine {lock.machine_id} falls within blackout"
                            )
            _validate_lock_windows_and_roles(self)
        if self.road_construction:
            seen_jobs: set[str] = set()
            for road_job in self.road_construction:
                if road_job.id in seen_jobs:
                    raise ValueError(
                        f"Duplicate road_construction id '{road_job.id}'. IDs must be unique."
                    )
                seen_jobs.add(road_job.id)

        if self.initial_state is not None:
            validate_initial_state(self)

        return self

    def shift_labels(self) -> set[str]:
        """Return the shift labels of the scenario's shift grid.

        These are the labels accepted for ``ScheduleLock.shift_id`` and used for the ``shift_id``
        column of solver and playback outputs. The source mirrors :meth:`Problem.from_scenario`.

        Returns
        -------
        set[str]
            ``shift_calendar`` labels when a shift calendar is present (whether or not each entry is
            available), otherwise the timeline shift names, otherwise ``{"S1"}`` (the synthetic
            single shift used for day-indexed scenarios).

        Examples
        --------
        >>> from fhops.scenario.io import load_scenario
        >>> load_scenario("examples/tiny7/scenario.yaml").shift_labels()
        {'S1'}
        """
        if self.shift_calendar:
            return {entry.shift_id for entry in self.shift_calendar}
        if self.timeline and self.timeline.shifts:
            return {shift_def.name for shift_def in self.timeline.shifts}
        return {"S1"}


ROLE_REMAINING_TOLERANCE = 1e-6
"""Volume tolerance (m³) when checking ``role_remaining <= work_required``.

Equal to the sequencing tracker's volume tolerance, so rolling-horizon carry-forward states built
from solver plans (which carry ~1e-7 m³ of solver noise) are not rejected."""


def _harvest_system_registry(scenario: Scenario) -> dict[str, HarvestSystem]:
    """Return the default harvest-system registry overlaid with ``scenario.harvest_systems``."""

    registry: dict[str, HarvestSystem] = dict(default_system_registry())
    if scenario.harvest_systems:
        registry.update(scenario.harvest_systems)
    return registry


def _validate_lock_windows_and_roles(scenario: Scenario) -> None:
    """Reject locks outside the block window or on a role the block's harvest system lacks.

    Called from :class:`Scenario` validation after the id/day/shift/blackout lock checks.

    Raises
    ------
    ValueError
        If a lock's ``day`` lies outside the block's ``[earliest_start, latest_finish]`` window
        (``latest_finish`` defaults to ``num_days``), or if the block declares
        ``harvest_system_id`` and the locked machine's ``role`` is missing or is not a role of that
        harvest system. Blocks without ``harvest_system_id`` accept any machine (unsequenced
        blocks). Blocks whose harvest system cannot be found in ``scenario.harvest_systems`` or
        the default registry are rejected earlier by :class:`Scenario` validation; when this helper
        is reached without that check (e.g. after ``model_copy``) they skip the role check.
    """

    locks = scenario.locked_assignments
    if not locks:
        return
    blocks = {block.id: block for block in scenario.blocks}
    machine_roles = {machine.id: machine.role for machine in scenario.machines}
    registry: dict[str, HarvestSystem] | None = None
    for lock in locks:
        block = blocks[lock.block_id]
        earliest = block.earliest_start if block.earliest_start is not None else 1
        latest = block.latest_finish if block.latest_finish is not None else scenario.num_days
        if not earliest <= lock.day <= latest:
            raise ValueError(
                f"Locked assignment for machine {lock.machine_id} on day {lock.day} falls outside "
                f"block {block.id} window [{earliest}, {latest}] "
                "(earliest_start/latest_finish)"
            )
        if not block.harvest_system_id:
            continue
        if registry is None:
            registry = _harvest_system_registry(scenario)
        system = registry.get(block.harvest_system_id)
        if system is None:
            continue
        system_roles = {job.machine_role for job in system.jobs if job.machine_role}
        role = machine_roles.get(lock.machine_id)
        if role not in system_roles:
            role_label = f"role {role}" if role else "no role"
            raise ValueError(
                f"Locked assignment for machine {lock.machine_id} ({role_label}) on block "
                f"{block.id} is incompatible with harvest system {system.system_id} "
                f"(roles: {', '.join(sorted(system_roles))})"
            )


def validate_initial_state(scenario: Scenario) -> None:
    """Validate ``scenario.initial_state`` against the scenario's blocks, machines, and systems.

    Called automatically by :class:`Scenario` validation (including the final re-validation in
    :func:`fhops.scenario.io.load_scenario`). Call it directly after attaching an
    ``initial_state`` with ``model_copy(update=...)``, which bypasses Pydantic validators.

    Parameters
    ----------
    scenario:
        Scenario whose ``initial_state`` should be checked. ``None`` initial state is accepted.

    Raises
    ------
    ValueError
        If a block/machine id is unknown, a ``last_block_id`` is not a scenario block, a block with
        role-keyed state has no ``harvest_system_id``, a role key is not a role of the block's
        harvest system, or a ``role_remaining`` value exceeds the block's ``work_required`` by more
        than ``ROLE_REMAINING_TOLERANCE`` (1e-6 m³; an upstream role can never have more left
        to output than the terminal volume still to deliver). Harvest systems are looked up in
        ``scenario.harvest_systems`` (falling back to
        :func:`fhops.scheduling.systems.default_system_registry`, mirroring
        :meth:`Problem.from_scenario`).
    """

    state = scenario.initial_state
    if state is None:
        return
    blocks = {block.id: block for block in scenario.blocks}
    machine_ids = {machine.id for machine in scenario.machines}
    registry = _harvest_system_registry(scenario)

    for block_state in state.blocks:
        block = blocks.get(block_state.block_id)
        if block is None:
            raise ValueError(f"initial_state references unknown block_id={block_state.block_id}")
        role_keys = (
            set(block_state.role_remaining)
            | set(block_state.staged_inventory)
            | set(block_state.role_shift_counts)
        )
        if not role_keys:
            continue
        if not block.harvest_system_id:
            raise ValueError(
                f"initial_state for block {block.id} sets role-keyed state but the block has no "
                "harvest_system_id"
            )
        system = registry.get(block.harvest_system_id)
        if system is None:
            raise ValueError(
                f"initial_state for block {block.id} references unknown harvest system "
                f"{block.harvest_system_id}"
            )
        system_roles = {job.machine_role for job in system.jobs if job.machine_role}
        unknown = sorted(role_keys - system_roles)
        if unknown:
            raise ValueError(
                f"initial_state for block {block.id} uses role(s) {', '.join(unknown)} that are not "
                f"roles of harvest system {system.system_id} "
                f"({', '.join(sorted(system_roles))})"
            )
        for role, remaining in sorted(block_state.role_remaining.items()):
            if remaining > block.work_required + ROLE_REMAINING_TOLERANCE:
                raise ValueError(
                    f"initial_state for block {block.id} sets role_remaining[{role!r}]={remaining} "
                    f"above the block's work_required={block.work_required}; a role cannot have "
                    "more volume left to output than the block still has to deliver"
                )

    for machine_state in state.machines:
        if machine_state.machine_id not in machine_ids:
            raise ValueError(
                f"initial_state references unknown machine_id={machine_state.machine_id}"
            )
        if machine_state.last_block_id is not None and machine_state.last_block_id not in blocks:
            raise ValueError(
                f"initial_state machine {machine_state.machine_id} references unknown "
                f"last_block_id={machine_state.last_block_id}"
            )


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
    "BlockInitialState",
    "MachineInitialState",
    "ScenarioInitialState",
    "validate_initial_state",
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
