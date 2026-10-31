"""Deterministic multi-machine ground-based harvesting simulation.

This module layers a grapple-skidder and loader queue onto the existing
single-machine tree-processing simulation. The feller-buncher still uses the
reference ADV6N10 processing time and spatial move model from
:mod:`fhops.spatial_machine`; the skidder and loader use configurable cycle
times. It is a reference execution model, not a field-calibrated system
simulation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np

from fhops.productivity.processor_loader import (
    estimate_loader_productivity_barko450,
    estimate_processor_productivity_adv5n6,
    estimate_processor_productivity_tn103,
)
from fhops.productivity.skidder_ft import (
    Han2018SkidderMethod,
    SkidderSpeedProfile,
    estimate_grapple_skidder_productivity_han2018,
    get_skidder_speed_profile,
)
from fhops.scenario.io import load_scenario
from fhops.spatial_machine import SpatialMachineError, simulate_block
from fhops.stem import StemInventory, build_stem_inventory
from fhops.terrain import TerrainError, TerrainRouter

GROUND_SYSTEM_SCHEMA = "fhops.tree.ground_system.v1"
DEFAULT_BUNCH_VOLUME_M3 = 8.0
DEFAULT_FELLER_REACH_M = 12.0
DEFAULT_FELLER_TRAVEL_SPEED_MPS = 0.8
DEFAULT_SKIDDER_CAPACITY_M3 = 40.0
DEFAULT_RATE_MODEL: Literal["calibrated", "reference"] = "calibrated"
RATE_MODELS = {"calibrated", "reference"}

__all__ = [
    "DEFAULT_BUNCH_VOLUME_M3",
    "DEFAULT_FELLER_REACH_M",
    "DEFAULT_FELLER_TRAVEL_SPEED_MPS",
    "DEFAULT_RATE_MODEL",
    "DEFAULT_SKIDDER_CAPACITY_M3",
    "GroundSystemError",
    "GroundSystemEvent",
    "GroundSystemResult",
    "GroundSystemTree",
    "BreakdownConfig",
    "DowntimeWindow",
    "PROCESSOR_MODELS",
    "ProcessorModel",
    "processor_spec_from_model",
    "generate_breakdown_windows",
    "MachineSpec",
    "default_loader_spec",
    "default_skidder_spec",
    "simulate_ground_system",
    "write_ground_system",
]


class GroundSystemError(RuntimeError):
    """Raised when a ground-based system simulation cannot be completed."""


@dataclass(frozen=True)
class MachineSpec:
    """Cycle-time parameters for one skidder or loader.

    Parameters
    ----------
    machine_id:
        Scenario machine identifier.
    machine_type:
        Human-readable machine type (``grapple_skidder`` or ``loader``).
    capacity_m3:
        Payload capacity in cubic metres. Only used by skidders.
    empty_speed_mps:
        Travel speed without a load, in metres per second.
    loaded_speed_mps:
        Travel speed with a load, in metres per second.
    load_fixed_s:
        Fixed loading time per bunch, seconds.
    load_per_log_s:
        Additional loading time per log, seconds.
    unload_fixed_s:
        Fixed unloading time per load, seconds.
    unload_per_log_s:
        Additional unloading time per log, seconds.
    process_fixed_s:
        Fixed loader processing time per load, seconds.
    process_per_log_s:
        Additional loader processing time per log, seconds.
    """

    machine_id: str
    machine_type: str
    capacity_m3: float = DEFAULT_SKIDDER_CAPACITY_M3
    empty_speed_mps: float = 1.4
    loaded_speed_mps: float = 1.1
    load_fixed_s: float = 45.0
    load_per_log_s: float = 5.0
    unload_fixed_s: float = 45.0
    unload_per_log_s: float = 3.0
    process_fixed_s: float = 45.0
    process_per_log_s: float = 4.0

    def __post_init__(self) -> None:
        for field, value in (
            ("capacity_m3", self.capacity_m3),
            ("empty_speed_mps", self.empty_speed_mps),
            ("loaded_speed_mps", self.loaded_speed_mps),
            ("load_fixed_s", self.load_fixed_s),
            ("load_per_log_s", self.load_per_log_s),
            ("unload_fixed_s", self.unload_fixed_s),
            ("unload_per_log_s", self.unload_per_log_s),
            ("process_fixed_s", self.process_fixed_s),
            ("process_per_log_s", self.process_per_log_s),
        ):
            if not math.isfinite(value) or value < 0:
                raise GroundSystemError(f"{field} must be finite and non-negative.")
        if self.capacity_m3 <= 0:
            raise GroundSystemError("capacity_m3 must be positive.")


@dataclass(frozen=True)
class ShiftPattern:
    """Daily operating-window pattern for system machines.

    Parameters
    ----------
    days:
        Number of operating days.
    shifts_per_day:
        Number of shifts per day.
    hours_per_shift:
        Productive hours in each shift.
    start_hour:
        Clock hour at which the first shift starts.

    Notes
    -----
    Tasks are not split across shift boundaries in this reference model. A task
    that does not fit in the remaining window is delayed to the next window.
    """

    days: int
    shifts_per_day: int = 1
    hours_per_shift: float = 10.0
    start_hour: float = 0.0

    def __post_init__(self) -> None:
        if self.days < 1:
            raise GroundSystemError("ShiftPattern.days must be >= 1.")
        if self.shifts_per_day < 1:
            raise GroundSystemError("ShiftPattern.shifts_per_day must be >= 1.")
        if not math.isfinite(self.hours_per_shift) or self.hours_per_shift <= 0:
            raise GroundSystemError("ShiftPattern.hours_per_shift must be positive.")
        if not math.isfinite(self.start_hour) or not 0 <= self.start_hour < 24:
            raise GroundSystemError("ShiftPattern.start_hour must be in [0, 24).")
        if self.start_hour + self.shifts_per_day * self.hours_per_shift > 24 + 1e-9:
            raise GroundSystemError("Shift windows cannot exceed a 24-hour day.")

    def windows(self) -> tuple[tuple[float, float], ...]:
        """Return absolute working windows in seconds from the simulation start."""
        windows: list[tuple[float, float]] = []
        for day in range(self.days):
            day_start = day * 86400.0
            for shift in range(self.shifts_per_day):
                start = day_start + (self.start_hour + shift * self.hours_per_shift) * 3600.0
                end = start + self.hours_per_shift * 3600.0
                windows.append((start, end))
        return tuple(windows)


@dataclass(frozen=True)
class DowntimeWindow:
    """Absolute machine downtime window.

    Parameters
    ----------
    machine_id:
        Machine affected by the downtime.
    start_s:
        Start time in seconds from simulation start.
    duration_s:
        Downtime duration in seconds.
    reason:
        Short reason label.
    """

    machine_id: str
    start_s: float
    duration_s: float
    reason: str = "downtime"

    def __post_init__(self) -> None:
        if not math.isfinite(self.start_s) or self.start_s < 0:
            raise GroundSystemError("DowntimeWindow.start_s must be finite and non-negative.")
        if not math.isfinite(self.duration_s) or self.duration_s <= 0:
            raise GroundSystemError("DowntimeWindow.duration_s must be positive and finite.")
        if not self.machine_id:
            raise GroundSystemError("DowntimeWindow.machine_id must be non-empty.")

    @property
    def end_s(self) -> float:
        """Return the absolute end time."""
        return self.start_s + self.duration_s


@dataclass(frozen=True)
class BreakdownConfig:
    """Seeded stochastic breakdown/repair configuration.

    Failures are generated in operating time, then queued through one repair
    crew. Repair duration is lognormal with mean ``repair_mean_hours`` and
    coefficient of variation ``repair_cv``.

    Parameters
    ----------
    failure_rate_per_machine_hour:
        Exponential failure rate per machine operating hour.
    repair_mean_hours:
        Mean repair duration in hours.
    repair_cv:
        Coefficient of variation for the lognormal repair duration.
    seed:
        Deterministic random seed.
    """

    failure_rate_per_machine_hour: float = 0.02
    repair_mean_hours: float = 2.0
    repair_cv: float = 0.5
    seed: int = 20261029

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.failure_rate_per_machine_hour)
            or self.failure_rate_per_machine_hour <= 0
        ):
            raise GroundSystemError("failure_rate_per_machine_hour must be positive and finite.")
        if not math.isfinite(self.repair_mean_hours) or self.repair_mean_hours <= 0:
            raise GroundSystemError("repair_mean_hours must be positive and finite.")
        if not math.isfinite(self.repair_cv) or self.repair_cv < 0:
            raise GroundSystemError("repair_cv must be finite and non-negative.")


@dataclass(frozen=True)
class TruckSpec:
    """Fixed-size log-truck fleet for landing dispatch.

    The fleet is deterministic: trucks become available every
    ``arrival_interval_s`` and after each round trip. Loading is scheduled
    inside the shift calendar when one is active.
    """

    capacity_m3: float
    cycle_time_s: float
    count: int = 1
    load_time_s: float = 300.0
    arrival_interval_s: float = 0.0
    one_way_distance_m: float | None = None
    speed_mps: float = 12.0
    mill_service_s: float = 600.0
    mill_bays: int = 1

    def __post_init__(self) -> None:
        for field, value in (
            ("capacity_m3", self.capacity_m3),
            ("cycle_time_s", self.cycle_time_s),
            ("load_time_s", self.load_time_s),
            ("speed_mps", self.speed_mps),
            ("mill_service_s", self.mill_service_s),
        ):
            if not math.isfinite(value) or value <= 0:
                raise GroundSystemError(f"TruckSpec.{field} must be positive and finite.")
        if not math.isfinite(self.arrival_interval_s) or self.arrival_interval_s < 0:
            raise GroundSystemError("TruckSpec.arrival_interval_s must be finite and non-negative.")
        if self.one_way_distance_m is not None and (
            not math.isfinite(self.one_way_distance_m) or self.one_way_distance_m <= 0
        ):
            raise GroundSystemError("TruckSpec.one_way_distance_m must be positive and finite.")
        if self.mill_bays < 1:
            raise GroundSystemError("TruckSpec.mill_bays must be >= 1.")
        if self.count < 1:
            raise GroundSystemError("TruckSpec.count must be >= 1.")


@dataclass(frozen=True)
class ProcessorSpec:
    """Cycle-time parameters for a roadside processor.

    Parameters
    ----------
    machine_id:
        Scenario machine identifier.
    seconds_per_m3:
        Productive seconds per cubic metre.
    fixed_s:
        Fixed per-load setup time in seconds.
    per_log_s:
        Additional processing time per bucked log, seconds.
    """

    machine_id: str
    seconds_per_m3: float = 3600.0 / 35.0
    fixed_s: float = 60.0
    per_log_s: float = 0.5

    def __post_init__(self) -> None:
        if not math.isfinite(self.seconds_per_m3) or self.seconds_per_m3 <= 0:
            raise GroundSystemError("ProcessorSpec.seconds_per_m3 must be positive and finite.")
        if not math.isfinite(self.fixed_s) or self.fixed_s < 0:
            raise GroundSystemError("ProcessorSpec.fixed_s must be finite and non-negative.")
        if not math.isfinite(self.per_log_s) or self.per_log_s < 0:
            raise GroundSystemError("ProcessorSpec.per_log_s must be finite and non-negative.")


ProcessorModel = Literal["tn103_area_a", "tn103_combined", "adv5n6_cold", "custom"]
PROCESSOR_MODELS = {"tn103_area_a", "tn103_combined", "adv5n6_cold", "custom"}


def processor_spec_from_model(
    machine_id: str,
    model: ProcessorModel,
    *,
    custom_rate_m3_per_smh: float | None = None,
) -> ProcessorSpec:
    """Return a processor specification for a named reference model."""
    rate: float | None
    if model == "custom":
        if custom_rate_m3_per_smh is None or custom_rate_m3_per_smh <= 0:
            raise GroundSystemError("custom processor model requires a positive rate.")
        rate = custom_rate_m3_per_smh
    elif model == "tn103_area_a":
        tn_result = estimate_processor_productivity_tn103(scenario="area_a_feller_bunched")
        rate = tn_result.productivity_m3_per_smh
    elif model == "tn103_combined":
        tn_combined = estimate_processor_productivity_tn103(scenario="combined_observed")
        rate = tn_combined.productivity_m3_per_smh
    elif model == "adv5n6_cold":
        adv_result = estimate_processor_productivity_adv5n6(
            stem_source="loader_forwarded", processing_mode="cold"
        )
        rate = adv_result.productivity_m3_per_smh
    else:
        raise GroundSystemError(f"Unknown processor model {model!r}.")
    if rate is None or not math.isfinite(rate) or rate <= 0:
        raise GroundSystemError(f"Processor model {model!r} has no usable productivity rate.")
    return ProcessorSpec(machine_id=machine_id, seconds_per_m3=3600.0 / rate)


def default_processor_spec(machine_id: str) -> ProcessorSpec:
    """Return a TN-103 feller-bunched processor specification."""
    return processor_spec_from_model(machine_id, "tn103_area_a")


def default_skidder_spec(machine_id: str) -> MachineSpec:
    """Return the default grapple-skidder specification for ``machine_id``."""
    return MachineSpec(machine_id=machine_id, machine_type="grapple_skidder")


def default_loader_spec(machine_id: str) -> MachineSpec:
    """Return the default loader specification for ``machine_id``."""
    return MachineSpec(machine_id=machine_id, machine_type="loader")


@dataclass(frozen=True)
class GroundSystemTree:
    """One tree processed by the feller-buncher."""

    tree_id: str
    x_m: float
    y_m: float
    dbh_cm: float
    merchantable_volume_m3: float
    log_count: int
    processed_s: float


@dataclass(frozen=True)
class GroundSystemEvent:
    """One machine-state segment in the system timeline."""

    machine: str
    type: str
    start_s: float
    end_s: float
    x0: float
    y0: float
    x1: float
    y1: float
    volume_m3: float = 0.0
    logs: int = 0
    tree_ids: tuple[str, ...] = ()
    status: str = ""
    distance_m: float = 0.0
    max_grade_percent: float = 0.0

    def to_dict(self) -> dict[str, object]:
        """Return the event as a JSON-serializable mapping."""
        return {
            "machine": self.machine,
            "type": self.type,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "volume_m3": self.volume_m3,
            "logs": self.logs,
            "tree_ids": list(self.tree_ids),
            "status": self.status,
            "distance_m": self.distance_m,
            "max_grade_percent": self.max_grade_percent,
        }


@dataclass(frozen=True)
class GroundSystemResult:
    """Result of one ground-based system on one block.

    Attributes
    ----------
    system_id:
        Deterministic identifier for the configuration and event stream.
    generated_utc:
        Generation timestamp.
    scenario_path:
        Scenario YAML.
    block_id:
        Block identifier.
    feller_machine_id:
        Feller-buncher machine identifier.
    skidder_machine_ids:
        Grapple-skidder identifiers.
    loader_machine_id:
        Loader identifier.
    landing_x_m, landing_y_m:
        Landing position in the block CRS.
    bunch_volume_m3:
        Target bunch volume.
    trees:
        Processed trees.
    events:
        Machine timeline.
    machine_summaries:
        Busy time and utilisation per machine.
    processed_volume_m3:
        Merchantable volume processed by the feller-buncher.
    tree_count:
        Processed tree count.
    unreachable_count:
        Trees refused by the feller-buncher.
    makespan_s:
        System makespan.
    warnings:
        Non-fatal observations.
    caveats:
        Model limits.
    """

    system_id: str
    generated_utc: str
    scenario_path: Path
    block_id: str
    feller_machine_id: str
    skidder_machine_ids: tuple[str, ...]
    loader_machine_id: str
    landing_x_m: float
    landing_y_m: float
    bunch_volume_m3: float
    rate_model: str
    rate_provenance: dict[str, object]
    shift_windows: tuple[tuple[float, float], ...]
    downtime_windows: tuple[DowntimeWindow, ...]
    breakdown_summary: dict[str, float | int] | None
    processor_machine_id: str | None
    processor_machine_ids: tuple[str, ...]
    truck_events: tuple[GroundSystemEvent, ...]
    truck_summary: dict[str, float | int] | None
    landing_inventory_final_m3: float
    landing_inventory_max_m3: float
    trees: tuple[GroundSystemTree, ...]
    events: tuple[GroundSystemEvent, ...]
    machine_summaries: dict[str, dict[str, float | int]]
    processed_volume_m3: float
    tree_count: int
    unreachable_count: int
    makespan_s: float
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the system manifest as a JSON-serializable mapping."""
        return {
            "schema_version": GROUND_SYSTEM_SCHEMA,
            "system_id": self.system_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "block_id": self.block_id,
            "feller_machine_id": self.feller_machine_id,
            "skidder_machine_ids": list(self.skidder_machine_ids),
            "loader_machine_id": self.loader_machine_id,
            "landing": {"x": self.landing_x_m, "y": self.landing_y_m},
            "bunch_volume_m3": self.bunch_volume_m3,
            "rate_model": self.rate_model,
            "rate_provenance": self.rate_provenance,
            "shift_windows": [list(window) for window in self.shift_windows],
            "downtime_windows": [
                {
                    "machine_id": window.machine_id,
                    "start_s": window.start_s,
                    "duration_s": window.duration_s,
                    "reason": window.reason,
                }
                for window in self.downtime_windows
            ],
            "breakdown_summary": self.breakdown_summary,
            "processor_machine_id": self.processor_machine_id,
            "processor_machine_ids": list(self.processor_machine_ids),
            "truck_events": [event.to_dict() for event in self.truck_events],
            "truck_summary": self.truck_summary,
            "landing_inventory_final_m3": self.landing_inventory_final_m3,
            "landing_inventory_max_m3": self.landing_inventory_max_m3,
            "tree_count": self.tree_count,
            "processed_volume_m3": self.processed_volume_m3,
            "unreachable_count": self.unreachable_count,
            "makespan_s": self.makespan_s,
            "machine_summaries": self.machine_summaries,
            "trees": [
                {
                    "tree_id": tree.tree_id,
                    "x": tree.x_m,
                    "y": tree.y_m,
                    "dbh_cm": tree.dbh_cm,
                    "volume_m3": tree.merchantable_volume_m3,
                    "logs": tree.log_count,
                    "processed_s": tree.processed_s,
                }
                for tree in self.trees
            ],
            "timeline": [event.to_dict() for event in self.events],
            "events": [event.to_dict() for event in self.events],
            "duration_s": self.makespan_s,
            "machines": {
                **{self.feller_machine_id: {"type": "feller_buncher"}},
                **{machine: {"type": "grapple_skidder"} for machine in self.skidder_machine_ids},
                **{
                    machine: {"type": "roadside_processor"}
                    for machine in self.processor_machine_ids
                },
                self.loader_machine_id: {"type": "loader"},
            },
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


def simulate_ground_system(
    scenario_path: str | Path,
    *,
    block_id: str,
    feller_machine_id: str,
    skidder_machine_ids: Sequence[str],
    loader_machine_id: str,
    processor_machine_id: str | None = None,
    processor_machine_ids: Sequence[str] | None = None,
    stem_inventory: StemInventory | None = None,
    landing_x_m: float | None = None,
    landing_y_m: float | None = None,
    bunch_volume_m3: float = DEFAULT_BUNCH_VOLUME_M3,
    rate_model: Literal["calibrated", "reference"] = DEFAULT_RATE_MODEL,
    dem_path: str | Path | None = None,
    road_path: str | Path | None = None,
    terrain_sample_step_m: float = 10.0,
    max_skidder_grade_percent: float = 35.0,
    terrain_speed_factor: float = 0.02,
    shift_days: int | None = None,
    shifts_per_day: int = 1,
    hours_per_shift: float = 10.0,
    shift_start_hour: float = 0.0,
    downtime: Sequence[DowntimeWindow] = (),
    breakdown_config: BreakdownConfig | None = None,
    truck_capacity_m3: float | None = None,
    truck_cycle_time_s: float = 3600.0,
    truck_count: int = 1,
    truck_load_time_s: float = 300.0,
    truck_arrival_interval_s: float = 0.0,
    truck_route_distance_m: float | None = None,
    truck_speed_mps: float = 12.0,
    mill_service_s: float = 600.0,
    mill_bays: int = 1,
    landing_capacity_m3: float | None = None,
    feller_reach_radius_m: float = DEFAULT_FELLER_REACH_M,
    feller_travel_speed_m_per_s: float = DEFAULT_FELLER_TRAVEL_SPEED_MPS,
    feller_processing_time_multiplier: float = 1.0,
    path_mode: Literal["nearest", "swath"] = "nearest",
    skidder_specs: Mapping[str, MachineSpec] | None = None,
    loader_spec: MachineSpec | None = None,
    processor_spec: ProcessorSpec | None = None,
    processor_specs: Mapping[str, ProcessorSpec] | None = None,
    processor_model: str | None = None,
    processor_rate_m3_per_smh: float | None = None,
    start_x_m: float | None = None,
    start_y_m: float | None = None,
    generated_utc: str | None = None,
) -> GroundSystemResult:
    """Simulate one feller-buncher/skidder/loader system on one block.

    The feller-buncher is simulated with :func:`fhops.spatial_machine.simulate_block`.
    Its processed-tree events are grouped into bunches. Skidders are dispatched
    greedily to the earliest available bunch, and the loader processes loads in
    arrival order. The model is deterministic for the same inputs.

    Parameters
    ----------
    scenario_path:
        Scenario YAML with a tree-inventory pin.
    block_id:
        Block to simulate.
    feller_machine_id:
        Scenario machine ID for the feller-buncher.
    skidder_machine_ids:
        One or more scenario machine IDs for grapple skidders.
    loader_machine_id:
        Scenario machine ID for the loader.
    processor_machine_id:
        Optional scenario roadside-processor machine ID between skidder and
        loader. Kept for single-processor callers.
    processor_machine_ids:
        Optional sequence of processor machine IDs. Use multiple processors
        for a parallel processing deck. Mutually exclusive with
        ``processor_machine_id``.
    stem_inventory:
        Optional precomputed stem inventory.
    landing_x_m, landing_y_m:
        Landing position. Defaults to the mean tree position.
    bunch_volume_m3:
        Target bunch volume in cubic metres.
    rate_model:
        ``calibrated`` uses the Han et al. (2018) grapple-skidder regression
        and the Barko 450 ground-skid loader result. ``reference`` uses the
        fixed cycle-time defaults in ``MachineSpec``.
    dem_path:
        Optional GeoTIFF DEM in the same CRS as the tree coordinates.
    road_path:
        Optional GeoJSON line in the same CRS. The route follows one connected
        road corridor between landing and bunch, then goes off-road.
    terrain_sample_step_m:
        DEM sampling interval along a route.
    max_skidder_grade_percent:
        Maximum allowed absolute route grade.
    terrain_speed_factor:
        Fractional speed loss per percent of mean absolute grade.
    shift_days:
        Optional number of operating days. When omitted, the model runs
        continuously.
    shifts_per_day:
        Shifts per operating day.
    hours_per_shift:
        Productive hours per shift.
    shift_start_hour:
        Clock hour when the first shift starts.
    downtime:
        Absolute machine downtime windows. Requires ``shift_days``.
    breakdown_config:
        Optional seeded stochastic breakdown/repair configuration. Requires
        ``shift_days``; repairs are serialized through one repair crew.
    truck_capacity_m3:
        Optional truck payload capacity. When omitted, trucking is not tracked.
    truck_cycle_time_s:
        Truck round-trip time excluding loading, seconds.
    truck_count:
        Number of trucks in the fleet.
    truck_load_time_s:
        Fixed truck loading time, seconds.
    truck_arrival_interval_s:
        Staggered initial truck arrival interval, seconds.
    truck_route_distance_m:
        Optional one-way landing-to-mill distance in metres. When supplied,
        truck cycle time is derived from distance/speed plus mill service.
    truck_speed_mps:
        Truck travel speed for route-derived cycles.
    mill_service_s:
        Mill service time per truck.
    mill_bays:
        Number of parallel mill service bays.
    landing_capacity_m3:
        Optional landing inventory capacity. Overflow is reported as a warning
        and does not block the loader in this reference model.
    feller_reach_radius_m:
        Feller-buncher reach in metres.
    feller_travel_speed_m_per_s:
        Feller-buncher travel speed.
    feller_processing_time_multiplier:
        Multiplier on feller-buncher per-tree processing time. Selection-cut
        care and other slow-work adjustments use values above one.
    path_mode:
        ``swath`` uses a boustrophedon feller path; ``nearest`` preserves the
        original nearest-tree behavior.
    skidder_specs:
        Optional per-skidder cycle-time overrides.
    loader_spec:
        Optional loader cycle-time override.
    processor_spec:
        Optional processor cycle-time override for a single processor.
    processor_specs:
        Optional per-processor cycle-time overrides.
    processor_model:
        Optional named processor model: ``tn103_area_a``, ``tn103_combined``,
        ``adv5n6_cold``, or ``custom``.
    processor_rate_m3_per_smh:
        Custom productive rate when ``processor_model="custom"``.
    start_x_m, start_y_m:
        Feller-buncher start position.
    generated_utc:
        Generation timestamp.

    Returns
    -------
    GroundSystemResult
        Event stream, tree list, machine summaries, and totals.

    Raises
    ------
    GroundSystemError
        If inputs are invalid or the feller-buncher simulation fails.
    """
    skidders = tuple(str(machine) for machine in skidder_machine_ids)
    if not skidders:
        raise GroundSystemError("At least one skidder machine is required.")
    if len(set(skidders)) != len(skidders):
        raise GroundSystemError("Skidder machine IDs must be unique.")
    if not math.isfinite(bunch_volume_m3) or bunch_volume_m3 <= 0:
        raise GroundSystemError("bunch_volume_m3 must be positive and finite.")
    if rate_model not in RATE_MODELS:
        raise GroundSystemError(f"rate_model must be one of {sorted(RATE_MODELS)}.")
    if feller_machine_id in skidders or loader_machine_id in skidders:
        raise GroundSystemError("Feller and loader machines must not also be skidders.")
    if feller_machine_id == loader_machine_id:
        raise GroundSystemError("Feller and loader machines must differ.")
    if processor_machine_id is not None and processor_machine_ids:
        raise GroundSystemError(
            "Pass either processor_machine_id or processor_machine_ids, not both."
        )
    processors = tuple(str(machine) for machine in (processor_machine_ids or ()))
    if processor_machine_id is not None:
        processors = (processor_machine_id,)
    if len(set(processors)) != len(processors):
        raise GroundSystemError("Processor machine IDs must be unique.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    try:
        scenario = load_scenario(scenario_file)
    except Exception as exc:  # noqa: BLE001 - preserve dependency error text
        raise GroundSystemError(str(exc)) from exc
    machines = {machine.id: machine for machine in scenario.machines}
    requested = (feller_machine_id, *skidders, loader_machine_id)
    requested = (*requested, *processors)
    missing = [machine for machine in requested if machine not in machines]
    if missing:
        raise GroundSystemError("Unknown scenario machine(s): " + ", ".join(missing))
    if machines[feller_machine_id].role not in {"feller_buncher", "harvester", "hand_faller"}:
        raise GroundSystemError(
            f"Feller machine {feller_machine_id!r} has role {machines[feller_machine_id].role!r}, "
            "expected feller_buncher/harvester/hand_faller."
        )
    for machine in skidders:
        if machines[machine].role not in {"grapple_skidder", "skidder"}:
            raise GroundSystemError(
                f"Skidder {machine!r} has role {machines[machine].role!r}, expected grapple_skidder/skidder."
            )
    if machines[loader_machine_id].role != "loader":
        raise GroundSystemError(
            f"Loader {loader_machine_id!r} has role {machines[loader_machine_id].role!r}, expected loader."
        )
    if processor_model is not None and processor_model not in PROCESSOR_MODELS:
        raise GroundSystemError(f"processor_model must be one of {sorted(PROCESSOR_MODELS)}.")
    if processor_model is not None and (processor_specs or processor_spec):
        raise GroundSystemError("Pass processor_model or explicit processor specs, not both.")
    processor_specs = dict(processor_specs or {})
    processor_models: dict[str, ProcessorSpec] = {}
    for machine in processors:
        if machines[machine].role not in {"roadside_processor", "processor"}:
            raise GroundSystemError(
                f"Processor {machine!r} has role {machines[machine].role!r}, "
                "expected roadside_processor/processor."
            )
        if processor_model is not None:
            processor_models[machine] = processor_spec_from_model(
                machine,
                processor_model,  # type: ignore[arg-type]
                custom_rate_m3_per_smh=processor_rate_m3_per_smh,
            )
        else:
            processor_models[machine] = processor_specs.get(machine) or default_processor_spec(
                machine
            )
        if processor_models[machine].machine_id != machine:
            raise GroundSystemError(f"Processor spec ID does not match {machine!r}.")
    if processor_spec is not None:
        if len(processors) != 1:
            raise GroundSystemError(
                "processor_spec is only valid with a single processor; use processor_specs."
            )
        processor_models[processors[0]] = processor_spec
    stems = stem_inventory
    if stems is None:
        try:
            stems = build_stem_inventory(scenario_file)
        except Exception as exc:  # noqa: BLE001 - preserve dependency error text
            raise GroundSystemError(str(exc)) from exc
    try:
        fb_sim = simulate_block(
            scenario_file,
            block_id=block_id,
            machine_id=feller_machine_id,
            stem_inventory=stems,
            start_x_m=start_x_m,
            start_y_m=start_y_m,
            reach_radius_m=feller_reach_radius_m,
            travel_speed_m_per_s=feller_travel_speed_m_per_s,
            processing_time_multiplier=feller_processing_time_multiplier,
            path_mode=path_mode,
        )
    except SpatialMachineError as exc:
        raise GroundSystemError(str(exc)) from exc
    trees_by_id = {tree.tree_id: tree for tree in stems.trees if tree.block_id == block_id}
    processed_events = [event for event in fb_sim.events if event.status == "processed"]
    if not processed_events:
        raise GroundSystemError(f"Block {block_id!r} produced no processed trees.")
    if landing_x_m is None or landing_y_m is None:
        landing_x = sum(tree.x_m for tree in processed_events) / len(processed_events)
        landing_y = sum(tree.y_m for tree in processed_events) / len(processed_events)
    else:
        landing_x, landing_y = landing_x_m, landing_y_m
    if not all(math.isfinite(value) for value in (landing_x, landing_y)):
        raise GroundSystemError("Landing position must be finite.")
    skidder_specs = dict(skidder_specs or {})
    for machine in skidders:
        skidder_specs.setdefault(machine, default_skidder_spec(machine))
        if skidder_specs[machine].machine_id != machine:
            raise GroundSystemError(
                f"Skidder spec ID {skidder_specs[machine].machine_id!r} does not match {machine!r}."
            )
    loader = loader_spec or default_loader_spec(loader_machine_id)
    if loader.machine_id != loader_machine_id:
        raise GroundSystemError("Loader spec ID does not match loader_machine_id.")
    speed_profile: SkidderSpeedProfile | None = None
    loader_seconds_per_m3: float | None = None
    rate_provenance: dict[str, object]
    if rate_model == "calibrated":
        speed_profile = get_skidder_speed_profile("SK")
        loader_result = estimate_loader_productivity_barko450(scenario="ground_skid_block")
        loader_seconds_per_m3 = 8.0 * 3600.0 / loader_result.avg_volume_per_shift_m3
        rate_provenance = {
            "skidder": {
                "model": "Han et al. (2018) whole-tree grapple-skidder regression",
                "speed_profile": speed_profile.key,
                "speed_profile_description": speed_profile.description,
            },
            "loader": {
                "model": "Barko 450 TN-46 ground-skid loader",
                "avg_volume_per_shift_m3": loader_result.avg_volume_per_shift_m3,
                "assumed_shift_hours": 8.0,
                "seconds_per_m3": loader_seconds_per_m3,
            },
        }
    else:
        rate_provenance = {"model": "reference fixed MachineSpec cycle times"}
    try:
        router = TerrainRouter(
            dem_path=dem_path,
            road_path=road_path,
            sample_step_m=terrain_sample_step_m,
            max_grade_percent=max_skidder_grade_percent,
            grade_speed_factor=terrain_speed_factor,
        )
    except TerrainError as exc:
        raise GroundSystemError(str(exc)) from exc
    rate_provenance["terrain"] = router.provenance()
    calendar: _ShiftCalendar | None = None
    shift_windows: tuple[tuple[float, float], ...] = ()
    downtime_windows = tuple(downtime)
    if (downtime_windows or breakdown_config is not None) and shift_days is None:
        raise GroundSystemError("downtime and breakdown_config require shift_days.")
    if shift_days is not None:
        pattern = ShiftPattern(
            days=shift_days,
            shifts_per_day=shifts_per_day,
            hours_per_shift=hours_per_shift,
            start_hour=shift_start_hour,
        )
        shift_windows = pattern.windows()
        breakdown_summary: dict[str, float | int] | None = None
        if breakdown_config is not None:
            machine_ids = (feller_machine_id, *skidders, loader_machine_id, *processors)
            generated, breakdown_summary = generate_breakdown_windows(
                machine_ids,
                shift_windows,
                breakdown_config,
            )
            downtime_windows = (*downtime_windows, *generated)
        calendar = _ShiftCalendar(pattern, downtime_windows)
    else:
        breakdown_summary = None
    truck_spec: TruckSpec | None = None
    if truck_capacity_m3 is not None:
        truck_spec = TruckSpec(
            capacity_m3=truck_capacity_m3,
            cycle_time_s=truck_cycle_time_s,
            count=truck_count,
            load_time_s=truck_load_time_s,
            arrival_interval_s=truck_arrival_interval_s,
            one_way_distance_m=truck_route_distance_m,
            speed_mps=truck_speed_mps,
            mill_service_s=mill_service_s,
            mill_bays=mill_bays,
        )
        if landing_capacity_m3 is None:
            landing_capacity_m3 = truck_spec.capacity_m3 * max(1, truck_spec.count) * 2.0
    if landing_capacity_m3 is not None and (
        not math.isfinite(landing_capacity_m3) or landing_capacity_m3 <= 0
    ):
        raise GroundSystemError("landing_capacity_m3 must be positive and finite.")
    rate_provenance["schedule"] = {
        "shift_days": shift_days,
        "shifts_per_day": shifts_per_day if shift_days is not None else None,
        "hours_per_shift": hours_per_shift if shift_days is not None else None,
        "shift_start_hour": shift_start_hour if shift_days is not None else None,
        "downtime": [
            {
                "machine_id": window.machine_id,
                "start_s": window.start_s,
                "duration_s": window.duration_s,
                "reason": window.reason,
            }
            for window in downtime_windows
        ],
        "breakdowns": breakdown_summary,
    }
    if truck_spec is not None:
        rate_provenance["trucking"] = {
            "capacity_m3": truck_spec.capacity_m3,
            "cycle_time_s": truck_spec.cycle_time_s,
            "count": truck_spec.count,
            "load_time_s": truck_spec.load_time_s,
            "arrival_interval_s": truck_spec.arrival_interval_s,
            "one_way_distance_m": truck_spec.one_way_distance_m or 0.0,
            "speed_mps": truck_spec.speed_mps,
            "mill_service_s": truck_spec.mill_service_s,
            "mill_bays": truck_spec.mill_bays,
            "landing_capacity_m3": landing_capacity_m3,
        }
    if processor_models:
        rate_provenance["processor"] = {
            "model": processor_model or ("custom_specs" if processor_specs else "tn103_area_a"),
            "model_description": "TN-103 feller-bunched processor"
            if processor_model in {None, "tn103_area_a", "tn103_combined"}
            else (
                "ADV5N6 cold loader-forwarded processor"
                if processor_model == "adv5n6_cold"
                else "custom processor rate"
            ),
            "machines": {
                machine: {
                    "seconds_per_m3": spec.seconds_per_m3,
                    "productivity_m3_per_smh": 3600.0 / spec.seconds_per_m3,
                    "fixed_s": spec.fixed_s,
                }
                for machine, spec in processor_models.items()
            },
        }
    events: list[GroundSystemEvent] = []
    trees: list[GroundSystemTree] = []
    previous_x = fb_sim.start_x_m
    previous_y = fb_sim.start_y_m
    fb_cursor = 0.0
    for event in processed_events:
        if calendar is None:
            travel_start = event.start_s
            travel_end = travel_start + event.move_time_s
            process_start = travel_end
            process_end = event.end_s
        else:
            if event.move_time_s > 0:
                travel_start, travel_end = calendar.schedule(
                    fb_cursor, event.move_time_s, feller_machine_id
                )
            else:
                travel_start = travel_end = fb_cursor
            process_start, process_end = calendar.schedule(
                travel_end, event.processing_time_s, feller_machine_id
            )
        if event.move_time_s > 0:
            events.append(
                GroundSystemEvent(
                    machine=feller_machine_id,
                    type="travel",
                    start_s=travel_start,
                    end_s=travel_end,
                    x0=previous_x,
                    y0=previous_y,
                    x1=event.machine_x_m,
                    y1=event.machine_y_m,
                    status="empty",
                )
            )
        events.append(
            GroundSystemEvent(
                machine=feller_machine_id,
                type="process",
                start_s=process_start,
                end_s=process_end,
                x0=event.machine_x_m,
                y0=event.machine_y_m,
                x1=event.machine_x_m,
                y1=event.machine_y_m,
                volume_m3=event.merchantable_volume_m3,
                logs=event.log_count,
                tree_ids=(event.tree_id,),
                status="processing",
            )
        )
        previous_x, previous_y = event.machine_x_m, event.machine_y_m
        fb_cursor = process_end
        trees.append(
            GroundSystemTree(
                tree_id=event.tree_id,
                x_m=event.x_m,
                y_m=event.y_m,
                dbh_cm=trees_by_id[event.tree_id].dbh_cm,
                merchantable_volume_m3=event.merchantable_volume_m3,
                log_count=event.log_count,
                processed_s=process_end,
            )
        )
    max_bunch_volume_m3 = min(spec.capacity_m3 for spec in skidder_specs.values())
    if bunch_volume_m3 > max_bunch_volume_m3 + 1e-9:
        raise GroundSystemError(
            f"bunch_volume_m3 ({bunch_volume_m3:.2f}) exceeds the smallest skidder capacity "
            f"({max_bunch_volume_m3:.2f} m3)."
        )
    bunches = _build_bunches(trees, bunch_volume_m3, max_bunch_volume_m3)
    try:
        loads = _simulate_skidders(
            events,
            bunches,
            skidders,
            skidder_specs,
            landing_x,
            landing_y,
            rate_model=rate_model,
            speed_profile=speed_profile,
            router=router,
            calendar=calendar,
        )
    except TerrainError as exc:
        router.close()
        raise GroundSystemError(str(exc)) from exc
    if processor_models:
        try:
            processor_total, loads = _simulate_processor(
                events,
                loads,
                processor_models,
                landing_x,
                landing_y,
                calendar=calendar,
            )
        except TerrainError as exc:
            router.close()
            raise GroundSystemError(str(exc)) from exc
    else:
        processor_total = 0.0
    try:
        (
            loader_total,
            load_finishes,
            truck_events,
            truck_summary,
            landing_final,
            landing_max,
            truck_warnings,
        ) = _simulate_loader(
            events,
            loads,
            loader,
            landing_x,
            landing_y,
            rate_model=rate_model,
            seconds_per_m3=loader_seconds_per_m3,
            calendar=calendar,
            truck_spec=truck_spec,
            landing_capacity_m3=landing_capacity_m3,
        )
    except TerrainError as exc:
        router.close()
        raise GroundSystemError(str(exc)) from exc
    fb_total = fb_cursor if calendar is not None else fb_sim.total_time_s
    skidder_total = max((load.ready_s for load in loads), default=0.0)
    truck_total = max((event.end_s for event in truck_events), default=0.0)
    makespan = max(fb_total, skidder_total, processor_total, loader_total, truck_total)
    summaries: dict[str, dict[str, float | int]] = {}
    machine_ids = (feller_machine_id, *skidders, loader_machine_id)
    machine_ids = (*machine_ids, *processors)
    for machine in machine_ids:
        machine_events = [event for event in events if event.machine == machine]
        busy = sum(event.end_s - event.start_s for event in machine_events)
        summaries[machine] = {
            "busy_s": busy,
            "events": len(machine_events),
            "utilisation": busy / makespan if makespan > 0 else 0.0,
        }
    material = {
        "block_id": block_id,
        "feller": feller_machine_id,
        "skidders": skidders,
        "loader": loader_machine_id,
        "processors": processors,
        "bunch_volume_m3": bunch_volume_m3,
        "rate_model": rate_model,
        "shift_days": shift_days,
        "truck_capacity_m3": truck_capacity_m3,
        "events": [event.to_dict() for event in events],
    }
    system_id = (
        "fhops-tree-system-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    events.sort(key=lambda event: (event.start_s, event.end_s, event.machine, event.type))
    warnings: list[str] = []
    if fb_sim.unreachable_count:
        warnings.append(
            f"{fb_sim.unreachable_count} tree(s) were unreachable by the feller-buncher."
        )
    warnings.extend(fb_sim.warnings)
    warnings.extend(truck_warnings)
    router.close()
    return GroundSystemResult(
        system_id=system_id,
        generated_utc=timestamp,
        scenario_path=scenario_file,
        block_id=block_id,
        feller_machine_id=feller_machine_id,
        skidder_machine_ids=skidders,
        loader_machine_id=loader_machine_id,
        landing_x_m=landing_x,
        landing_y_m=landing_y,
        bunch_volume_m3=bunch_volume_m3,
        rate_model=rate_model,
        rate_provenance=rate_provenance,
        shift_windows=shift_windows,
        downtime_windows=downtime_windows,
        breakdown_summary=breakdown_summary,
        processor_machine_id=processors[0] if processors else None,
        processor_machine_ids=processors,
        truck_events=tuple(truck_events),
        truck_summary=truck_summary,
        landing_inventory_final_m3=landing_final,
        landing_inventory_max_m3=landing_max,
        trees=tuple(trees),
        events=tuple(events),
        machine_summaries=summaries,
        processed_volume_m3=sum(tree.merchantable_volume_m3 for tree in trees),
        tree_count=len(trees),
        unreachable_count=fb_sim.unreachable_count,
        makespan_s=makespan,
        warnings=tuple(warnings),
        caveats=(
            "Reference multi-machine event model, not a field-calibrated system simulation.",
            "Feller-buncher processing uses the existing reference spatial/ADV6N10 model.",
            "Skidder, processor, and loader cycle times are configurable defaults; queue dispatch is greedy and deterministic.",
            "DEM/road routing is optional; the model uses a direct line or a single connected road corridor and does not solve a full road network.",
            "Shift windows delay tasks that do not fit; tasks are not split across shifts.",
            "Trucking blocks the loader when landing inventory would exceed capacity; partial truck loads are allowed to make space.",
            "Tree lists must be reviewed separately; this module does not validate stem-model calibration.",
        ),
    )


@dataclass(frozen=True)
class _Bunch:
    bunch_id: str
    tree_ids: tuple[str, ...]
    volume_m3: float
    logs: int
    ready_s: float
    x: float
    y: float


@dataclass(frozen=True)
class _Load:
    load_id: str
    bunch_id: str
    skidder_id: str
    volume_m3: float
    logs: int
    ready_s: float
    tree_ids: tuple[str, ...]


def generate_breakdown_windows(
    machine_ids: Sequence[str],
    shift_windows: Sequence[tuple[float, float]],
    config: BreakdownConfig,
) -> tuple[tuple[DowntimeWindow, ...], dict[str, float | int]]:
    """Generate seeded breakdown windows and route repairs through one crew."""
    if not shift_windows:
        raise GroundSystemError("Breakdown generation requires shift windows.")
    segments: list[tuple[float, float, float, float]] = []
    active_cursor = 0.0
    for window_start, window_end in shift_windows:
        duration = window_end - window_start
        if duration <= 0:
            continue
        segments.append((active_cursor, active_cursor + duration, window_start, window_end))
        active_cursor += duration
    total_active_seconds = active_cursor
    if total_active_seconds <= 0:
        raise GroundSystemError("Breakdown generation requires positive shift windows.")

    def active_to_wall(active_seconds: float) -> float:
        for active_start, active_end, wall_start, _wall_end in segments:
            if active_seconds <= active_end + 1e-9:
                return wall_start + (active_seconds - active_start)
        return segments[-1][3]

    rng = np.random.default_rng(config.seed)
    failures: list[tuple[float, str, float]] = []
    sigma = math.sqrt(math.log1p(config.repair_cv**2)) if config.repair_cv > 0 else 0.0
    for machine in machine_ids:
        active = 0.0
        while True:
            active += float(rng.exponential(1.0 / config.failure_rate_per_machine_hour)) * 3600.0
            if active > total_active_seconds:
                break
            failure_time = active_to_wall(active)
            repair_hours = float(
                rng.lognormal(
                    mean=math.log(config.repair_mean_hours) - 0.5 * sigma**2,
                    sigma=sigma,
                )
            )
            failures.append((failure_time, machine, repair_hours))
    failures.sort(key=lambda item: (item[0], item[1]))
    crew_available = 0.0
    last_end: dict[str, float] = {}
    windows: list[DowntimeWindow] = []
    crew_wait = 0.0
    for failure_time, machine, repair_hours in failures:
        if failure_time < last_end.get(machine, 0.0):
            continue
        repair_start = max(failure_time, crew_available)
        repair_end = repair_start + repair_hours * 3600.0
        if repair_end <= failure_time:
            continue
        crew_wait += repair_start - failure_time
        windows.append(
            DowntimeWindow(
                machine_id=machine,
                start_s=failure_time,
                duration_s=repair_end - failure_time,
                reason="breakdown",
            )
        )
        crew_available = repair_end
        last_end[machine] = repair_end
    summary: dict[str, float | int] = {
        "seed": config.seed,
        "failure_count": len(windows),
        "repair_hours": round(sum(item.duration_s for item in windows) / 3600.0, 3),
        "crew_wait_hours": round(crew_wait / 3600.0, 3),
        "failure_rate_per_machine_hour": config.failure_rate_per_machine_hour,
        "repair_mean_hours": config.repair_mean_hours,
        "repair_cv": config.repair_cv,
    }
    return tuple(windows), summary


class _ShiftCalendar:
    def __init__(
        self,
        pattern: ShiftPattern,
        downtime: Sequence[DowntimeWindow] = (),
    ) -> None:
        self.windows = pattern.windows()
        self.downtime: dict[str, list[DowntimeWindow]] = {}
        for window in downtime:
            self.downtime.setdefault(window.machine_id, []).append(window)

    def schedule(
        self,
        start_s: float,
        duration_s: float,
        machine_id: str | None = None,
    ) -> tuple[float, float]:
        if duration_s <= 0:
            return start_s, start_s
        blocks = self.downtime.get(machine_id or "", [])
        for window_start, window_end in self.windows:
            candidate = max(start_s, window_start)
            while True:
                overlapping = [
                    block
                    for block in blocks
                    if candidate < block.end_s and candidate + duration_s > block.start_s
                ]
                if not overlapping:
                    break
                candidate = max(block.end_s for block in overlapping)
            if candidate + duration_s <= window_end + 1e-9:
                return candidate, candidate + duration_s
        raise GroundSystemError(
            f"Task of {duration_s / 3600.0:.2f} h does not fit in the remaining operating windows."
        )


def _schedule_task(
    calendar: _ShiftCalendar | None,
    start_s: float,
    duration_s: float,
    machine_id: str | None = None,
) -> tuple[float, float]:
    if calendar is None:
        return start_s, start_s + duration_s
    return calendar.schedule(start_s, duration_s, machine_id)


def _build_bunches(
    trees: list[GroundSystemTree],
    target_volume_m3: float,
    max_volume_m3: float,
) -> list[_Bunch]:
    bunches: list[_Bunch] = []
    current: list[GroundSystemTree] = []
    volume = 0.0

    def flush() -> None:
        nonlocal current, volume
        if not current:
            return
        last = current[-1]
        bunches.append(
            _Bunch(
                bunch_id=f"B{len(bunches) + 1:05d}",
                tree_ids=tuple(item.tree_id for item in current),
                volume_m3=volume,
                logs=sum(item.log_count for item in current),
                ready_s=last.processed_s,
                x=last.x_m,
                y=last.y_m,
            )
        )
        current = []
        volume = 0.0

    for tree in trees:
        if tree.merchantable_volume_m3 > max_volume_m3 + 1e-9:
            raise GroundSystemError(
                f"Tree {tree.tree_id!r} ({tree.merchantable_volume_m3:.2f} m3) exceeds "
                f"skidder capacity ({max_volume_m3:.2f} m3)."
            )
        if current and volume + tree.merchantable_volume_m3 > max_volume_m3:
            flush()
        current.append(tree)
        volume += tree.merchantable_volume_m3
        if volume >= target_volume_m3:
            flush()
    flush()
    return bunches


def _simulate_skidders(
    events: list[GroundSystemEvent],
    bunches: list[_Bunch],
    skidder_ids: tuple[str, ...],
    specs: Mapping[str, MachineSpec],
    landing_x: float,
    landing_y: float,
    *,
    rate_model: str,
    speed_profile: SkidderSpeedProfile | None,
    router: TerrainRouter,
    calendar: _ShiftCalendar | None,
) -> list[_Load]:
    loads: list[_Load] = []
    available = {machine: 0.0 for machine in skidder_ids}
    for bunch in bunches:
        machine = min(skidder_ids, key=lambda item: available[item])
        spec = specs[machine]
        if bunch.volume_m3 > spec.capacity_m3 + 1e-9:
            raise GroundSystemError(
                f"Bunch {bunch.bunch_id} ({bunch.volume_m3:.2f} m3) exceeds "
                f"{machine} capacity ({spec.capacity_m3:.2f} m3)."
            )
        start = available[machine]
        bx, by = bunch.x, bunch.y
        route = router.route((landing_x, landing_y), (bx, by))
        distance = route.distance_m
        empty_start = start
        if rate_model == "calibrated":
            if speed_profile is None:
                raise GroundSystemError("Calibrated rate model requires a skidder speed profile.")
            empty_speed = speed_profile.empty_speed_kmh * (1000.0 / 3600.0)
            loaded_speed = speed_profile.loaded_speed_kmh * (1000.0 / 3600.0)
            empty_time = distance / (empty_speed * route.speed_factor)
            loaded_time = distance / (loaded_speed * route.speed_factor)
            cycle = estimate_grapple_skidder_productivity_han2018(
                method=Han2018SkidderMethod.WHOLE_TREE,
                pieces_per_cycle=float(len(bunch.tree_ids)),
                piece_volume_m3=bunch.volume_m3 / max(1, len(bunch.tree_ids)),
                empty_distance_m=distance,
                loaded_distance_m=distance,
                speed_profile=speed_profile,
            ).cycle_time_seconds
            residual = max(1.0, cycle - empty_time - loaded_time)
            load_time = residual * 0.5
            unload_time = residual * 0.5
        else:
            empty_time = distance / (spec.empty_speed_mps * route.speed_factor)
            loaded_time = distance / (spec.loaded_speed_mps * route.speed_factor)
            # Reference skidder time is per whole tree, not per bucked log.
            pieces = len(bunch.tree_ids)
            load_time = spec.load_fixed_s + spec.load_per_log_s * pieces
            unload_time = spec.unload_fixed_s + spec.unload_per_log_s * pieces
        empty_start, empty_end = _schedule_task(calendar, empty_start, empty_time, machine)
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="travel_empty",
                start_s=empty_start,
                end_s=empty_end,
                x0=landing_x,
                y0=landing_y,
                x1=bx,
                y1=by,
                status="empty",
                distance_m=route.distance_m,
                max_grade_percent=route.max_grade_percent,
            )
        )
        load_start = max(empty_end, bunch.ready_s)
        load_start, load_end = _schedule_task(calendar, load_start, load_time, machine)
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="load",
                start_s=load_start,
                end_s=load_end,
                x0=bx,
                y0=by,
                x1=bx,
                y1=by,
                volume_m3=bunch.volume_m3,
                logs=bunch.logs,
                tree_ids=bunch.tree_ids,
                status="loading",
            )
        )
        loaded_end = _schedule_task(calendar, load_end, loaded_time, machine)[1]
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="travel_loaded",
                start_s=load_end,
                end_s=loaded_end,
                x0=bx,
                y0=by,
                x1=landing_x,
                y1=landing_y,
                volume_m3=bunch.volume_m3,
                logs=bunch.logs,
                status="loaded",
                distance_m=route.distance_m,
                max_grade_percent=route.max_grade_percent,
            )
        )
        unload_end = _schedule_task(calendar, loaded_end, unload_time, machine)[1]
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="unload",
                start_s=loaded_end,
                end_s=unload_end,
                x0=landing_x,
                y0=landing_y,
                x1=landing_x,
                y1=landing_y,
                volume_m3=bunch.volume_m3,
                logs=bunch.logs,
                status="unloading",
            )
        )
        available[machine] = unload_end
        loads.append(
            _Load(
                load_id=f"L{len(loads) + 1:05d}",
                bunch_id=bunch.bunch_id,
                skidder_id=machine,
                volume_m3=bunch.volume_m3,
                logs=bunch.logs,
                ready_s=unload_end,
                tree_ids=bunch.tree_ids,
            )
        )
    return loads


def _simulate_processor(
    events: list[GroundSystemEvent],
    loads: list[_Load],
    specs: Mapping[str, ProcessorSpec],
    landing_x: float,
    landing_y: float,
    *,
    calendar: _ShiftCalendar | None,
) -> tuple[float, list[_Load]]:
    processors = tuple(specs)
    available = {machine: 0.0 for machine in processors}
    processed: list[_Load] = []
    for load in sorted(loads, key=lambda item: (item.ready_s, item.load_id)):
        machine = min(processors, key=lambda item: available[item])
        spec = specs[machine]
        start = max(available[machine], load.ready_s)
        duration = spec.fixed_s + spec.seconds_per_m3 * load.volume_m3 + spec.per_log_s * load.logs
        start, end = _schedule_task(calendar, start, duration, spec.machine_id)
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="process",
                start_s=start,
                end_s=end,
                x0=landing_x,
                y0=landing_y,
                x1=landing_x,
                y1=landing_y,
                volume_m3=load.volume_m3,
                logs=load.logs,
                tree_ids=load.tree_ids,
                status="processing",
            )
        )
        processed.append(
            _Load(
                load_id=load.load_id,
                bunch_id=load.bunch_id,
                skidder_id=load.skidder_id,
                volume_m3=load.volume_m3,
                logs=load.logs,
                ready_s=end,
                tree_ids=load.tree_ids,
            )
        )
        available[machine] = end
    return max(available.values(), default=0.0), processed


def _simulate_loader(
    events: list[GroundSystemEvent],
    loads: list[_Load],
    spec: MachineSpec,
    landing_x: float,
    landing_y: float,
    *,
    rate_model: str,
    seconds_per_m3: float | None,
    calendar: _ShiftCalendar | None,
    truck_spec: TruckSpec | None,
    landing_capacity_m3: float | None,
) -> tuple[
    float,
    dict[str, float],
    list[GroundSystemEvent],
    dict[str, float | int] | None,
    float,
    float,
    list[str],
]:
    available = 0.0
    finishes: dict[str, float] = {}
    truck_events: list[GroundSystemEvent] = []
    truck_available = (
        [index * truck_spec.arrival_interval_s for index in range(truck_spec.count)]
        if truck_spec
        else []
    )
    mill_available = [0.0] * (truck_spec.mill_bays if truck_spec else 0)
    mill_wait_s = 0.0
    inventory = 0.0
    max_inventory = 0.0
    dispatched = 0
    dispatched_volume = 0.0
    warnings: list[str] = []

    def dispatch_truck(start_s: float) -> tuple[float, float]:
        nonlocal inventory, dispatched, dispatched_volume
        if truck_spec is None or inventory <= 1e-9:
            return start_s, 0.0
        truck_index = min(range(truck_spec.count), key=lambda index: truck_available[index])
        start = max(start_s, truck_available[truck_index])
        load_volume = min(truck_spec.capacity_m3, inventory)
        truck_id = f"T-{truck_index + 1:02d}"
        start, load_end = _schedule_task(calendar, start, truck_spec.load_time_s, truck_id)
        if truck_spec.one_way_distance_m is not None:
            nonlocal mill_wait_s
            travel_s = truck_spec.one_way_distance_m / truck_spec.speed_mps
            arrival = load_end + travel_s
            bay = min(range(truck_spec.mill_bays), key=lambda index: mill_available[index])
            service_start = max(arrival, mill_available[bay])
            mill_wait_s += service_start - arrival
            service_end = service_start + truck_spec.mill_service_s
            mill_available[bay] = service_end
            return_end = service_end + travel_s
        else:
            return_end = load_end + truck_spec.cycle_time_s
        truck_events.append(
            GroundSystemEvent(
                machine=truck_id,
                type="truck_load",
                start_s=start,
                end_s=load_end,
                x0=landing_x,
                y0=landing_y,
                x1=landing_x,
                y1=landing_y,
                volume_m3=load_volume,
                status="loading",
            )
        )
        truck_events.append(
            GroundSystemEvent(
                machine=truck_id,
                type="truck_return",
                start_s=load_end,
                end_s=return_end,
                x0=landing_x,
                y0=landing_y,
                x1=landing_x,
                y1=landing_y,
                volume_m3=load_volume,
                status="returning",
            )
        )
        inventory -= load_volume
        dispatched += 1
        dispatched_volume += load_volume
        truck_available[truck_index] = return_end
        return start, load_volume

    for load in sorted(loads, key=lambda item: (item.ready_s, item.load_id)):
        start = max(available, load.ready_s)
        if rate_model == "calibrated":
            if seconds_per_m3 is None:
                raise GroundSystemError("Calibrated rate model requires loader seconds per m3.")
            process_time = seconds_per_m3 * load.volume_m3
            process_time += spec.process_per_log_s * load.logs
        else:
            process_time = spec.process_fixed_s + spec.process_per_log_s * load.logs
        if truck_spec is not None and landing_capacity_m3 is not None:
            while inventory + load.volume_m3 > landing_capacity_m3 + 1e-9:
                if inventory <= 1e-9:
                    raise GroundSystemError(
                        f"Landing capacity {landing_capacity_m3:.2f} m3 is smaller than load "
                        f"{load.load_id} ({load.volume_m3:.2f} m3)."
                    )
                truck_index = min(range(truck_spec.count), key=lambda index: truck_available[index])
                wait_until = max(start, truck_available[truck_index])
                truck_start, _ = dispatch_truck(wait_until)
                start = max(start, truck_start)
        start, end = _schedule_task(calendar, start, process_time)
        events.append(
            GroundSystemEvent(
                machine=spec.machine_id,
                type="process",
                start_s=start,
                end_s=end,
                x0=landing_x,
                y0=landing_y,
                x1=landing_x,
                y1=landing_y,
                volume_m3=load.volume_m3,
                logs=load.logs,
                tree_ids=load.tree_ids,
                status="processing",
            )
        )
        inventory += load.volume_m3
        max_inventory = max(max_inventory, inventory)
        available = end
        finishes[load.load_id] = end
        if truck_spec is not None:
            while inventory >= truck_spec.capacity_m3 - 1e-9:
                ready_truck = min(truck_available)
                if ready_truck > available:
                    break
                dispatch_truck(available)
    if truck_spec is None:
        return available, finishes, [], None, 0.0, 0.0, []
    while inventory >= truck_spec.capacity_m3 - 1e-9:
        ready_truck = min(truck_available)
        if ready_truck > max(available, max((event.end_s for event in truck_events), default=0.0)):
            break
        dispatch_truck(max(available, ready_truck))
    truck_total = max((event.end_s for event in truck_events), default=0.0)
    summary: dict[str, float | int] = {
        "truck_count": truck_spec.count,
        "truck_capacity_m3": truck_spec.capacity_m3,
        "arrival_interval_s": truck_spec.arrival_interval_s,
        "one_way_distance_m": truck_spec.one_way_distance_m or 0.0,
        "speed_mps": truck_spec.speed_mps,
        "mill_service_s": truck_spec.mill_service_s,
        "mill_bays": truck_spec.mill_bays,
        "mill_wait_s": round(mill_wait_s, 3),
        "dispatched_loads": dispatched,
        "dispatched_volume_m3": round(dispatched_volume, 3),
        "landing_inventory_final_m3": round(inventory, 3),
        "landing_inventory_max_m3": round(max_inventory, 3),
        "landing_capacity_m3": landing_capacity_m3 or 0.0,
        "truck_total_s": round(truck_total, 3),
    }
    if landing_capacity_m3 is not None and max_inventory > landing_capacity_m3 + 1e-9:
        warnings.append(
            f"Landing inventory peaked at {max_inventory:.2f} m3, above capacity "
            f"{landing_capacity_m3:.2f} m3."
        )
    return available, finishes, truck_events, summary, inventory, max_inventory, warnings


def write_ground_system(result: GroundSystemResult, out_dir: Path) -> dict[str, Path]:
    """Write ground-system events, trees, and the summary manifest.

    Parameters
    ----------
    result:
        Ground-system result.
    out_dir:
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``events_csv``, ``events_json``, ``trees_csv``, and
        ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    events_csv = output / "system_events.csv"
    with events_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "machine",
                "type",
                "start_s",
                "end_s",
                "x0",
                "y0",
                "x1",
                "y1",
                "volume_m3",
                "logs",
                "tree_ids",
                "status",
            )
        )
        for event in result.events:
            writer.writerow(
                (
                    event.machine,
                    event.type,
                    event.start_s,
                    event.end_s,
                    event.x0,
                    event.y0,
                    event.x1,
                    event.y1,
                    event.volume_m3,
                    event.logs,
                    ";".join(event.tree_ids),
                    event.status,
                    event.distance_m,
                    event.max_grade_percent,
                )
            )
    trees_csv = output / "tree_processing.csv"
    with trees_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "tree_id",
                "x_m",
                "y_m",
                "dbh_cm",
                "merchantable_volume_m3",
                "log_count",
                "processed_s",
            )
        )
        for tree in result.trees:
            writer.writerow(
                (
                    tree.tree_id,
                    tree.x_m,
                    tree.y_m,
                    tree.dbh_cm,
                    tree.merchantable_volume_m3,
                    tree.log_count,
                    tree.processed_s,
                )
            )
    events_json = output / "system_events.json"
    events_json.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = output / "system_summary.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": GROUND_SYSTEM_SCHEMA,
                "system_id": result.system_id,
                "block_id": result.block_id,
                "tree_count": result.tree_count,
                "processed_volume_m3": result.processed_volume_m3,
                "unreachable_count": result.unreachable_count,
                "makespan_s": result.makespan_s,
                "shift_windows": [list(window) for window in result.shift_windows],
                "downtime_windows": [
                    {
                        "machine_id": window.machine_id,
                        "start_s": window.start_s,
                        "duration_s": window.duration_s,
                        "reason": window.reason,
                    }
                    for window in result.downtime_windows
                ],
                "breakdown_summary": result.breakdown_summary,
                "truck_summary": result.truck_summary,
                "landing_inventory_final_m3": result.landing_inventory_final_m3,
                "landing_inventory_max_m3": result.landing_inventory_max_m3,
                "rate_model": result.rate_model,
                "rate_provenance": result.rate_provenance,
                "machine_summaries": result.machine_summaries,
                "warnings": list(result.warnings),
                "caveats": list(result.caveats),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "events_csv": events_csv,
        "events_json": events_json,
        "trees_csv": trees_csv,
        "manifest": manifest,
    }
