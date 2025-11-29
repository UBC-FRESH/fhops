"""Deterministic playback primitives."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fhops.scenario.contract import Problem

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    import pandas as pd

__all__ = [
    "PlaybackConfig",
    "PlaybackRecord",
    "ShiftSummary",
    "DaySummary",
    "PlaybackResult",
    "run_playback",
    "summarise_shifts",
    "summarise_days",
]


@dataclass(slots=True)
class PlaybackConfig:
    """Tuning options for deterministic playback execution."""

    respect_blackouts: bool = True
    infer_missing_shifts: bool = True
    include_idle_records: bool = False  # TODO: emit idle rows once availability bridge lands.


@dataclass(slots=True)
class PlaybackRecord:
    """Atomic shift-level record produced by deterministic playback."""

    day: int
    shift_id: str
    machine_id: str
    block_id: str | None
    hours_worked: float | None = None
    production_units: float | None = None
    mobilisation_cost: float | None = None
    blackout_hit: bool = False
    landing_id: str | None = None
    machine_role: str | None = None
    downtime: bool = False
    weather_severity: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    sample_id: int = 0


@dataclass(slots=True)
class ShiftSummary:
    """Aggregated metrics per machine/shift."""

    day: int
    shift_id: str
    machine_id: str
    machine_role: str | None = None
    available_hours: float = 0.0
    total_hours: float = 0.0
    production_units: float = 0.0
    mobilisation_cost: float = 0.0
    idle_hours: float | None = None
    blackout_conflicts: int = 0
    sequencing_violations: int = 0
    utilisation_ratio: float | None = None
    sample_id: int = 0
    downtime_hours: float = 0.0
    downtime_events: int = 0
    weather_severity_total: float = 0.0


@dataclass(slots=True)
class DaySummary:
    """Aggregated metrics per day across machines."""

    day: int
    available_hours: float = 0.0
    total_hours: float = 0.0
    production_units: float = 0.0
    mobilisation_cost: float = 0.0
    completed_blocks: int = 0
    idle_hours: float | None = None
    blackout_conflicts: int = 0
    sequencing_violations: int = 0
    utilisation_ratio: float | None = None
    sample_id: int = 0
    downtime_hours: float = 0.0
    downtime_events: int = 0
    weather_severity_total: float = 0.0


@dataclass(slots=True)
class PlaybackResult:
    """Container grouping playback outputs."""

    records: Sequence[PlaybackRecord]
    shift_summaries: Sequence[ShiftSummary]
    day_summaries: Sequence[DaySummary]
    config: PlaybackConfig
    sequencing_debug: dict[str, object] | None = None
    sample_id: int = 0


def run_playback(
    problem: Problem,
    assignments: pd.DataFrame,
    *,
    config: PlaybackConfig | None = None,
    sample_id: int = 0,
) -> PlaybackResult:
    """Convert solver assignments into playback records and aggregated summaries."""

    cfg = config or PlaybackConfig()
    availability_map = _compute_shift_availability(problem, cfg)

    from .adapters import assignments_to_records  # Local import to avoid circular dependency.

    record_iter = assignments_to_records(problem, assignments)

    # Materialise records since downstream summaries iterate multiple times.
    records: tuple[PlaybackRecord, ...] = tuple(record_iter)
    sequencing_debug: dict[str, object] | None = None
    tracker = getattr(record_iter, "sequencing_tracker", None)
    if tracker is not None:
        sequencing_debug = tracker.debug_snapshot()

    shift_summaries = tuple(
        summarise_shifts(
            records,
            availability_map,
            include_idle=cfg.include_idle_records,
            sample_id=sample_id,
        )
    )
    completed_by_day: dict[int, set[str]] = defaultdict(set)
    for record in records:
        if record.block_id and record.metadata.get("block_completed"):
            completed_by_day[record.day].add(record.block_id)
    day_summaries = tuple(
        summarise_days(
            shift_summaries,
            availability_map,
            completed_by_day,
            sample_id=sample_id,
        )
    )

    if cfg.respect_blackouts:
        # When respecting blackouts, flag entries already emitted; future iterations may
        # choose to filter or adjust scheduling, but caller still receives full trace.
        pass

    return PlaybackResult(
        records=records,
        shift_summaries=shift_summaries,
        day_summaries=day_summaries,
        config=cfg,
        sequencing_debug=sequencing_debug,
        sample_id=sample_id,
    )


def summarise_shifts(
    records: Iterable[PlaybackRecord],
    availability_map: dict[tuple[int, str, str], float],
    *,
    include_idle: bool = False,
    sample_id: int = 0,
) -> Iterator[ShiftSummary]:
    """Aggregate playback records to machine/shift summaries.

    Parameters
    ----------
    records:
        Iterator of :class:`PlaybackRecord` instances produced by ``assignments_to_records``.
    availability_map:
        Mapping ``(day, shift_id, machine_id) -> available_hours`` computed via
        ``_compute_shift_availability``; used to seed summaries and compute utilisation ratios.
    include_idle:
        When ``True``, emit summaries for every availability entry even if no work occurred
        (resulting in ``total_hours = 0`` but preserving the availability baseline).
    sample_id:
        Identifier propagated through stochastic playback so downstream aggregations can group rows.
    """

    aggregates: dict[tuple[int, str, str], ShiftSummary] = {}
    seen: set[tuple[int, str, str]] = set()

    if include_idle:
        for (day, shift_id, machine_id), available_hours in availability_map.items():
            aggregates[(day, shift_id, machine_id)] = ShiftSummary(
                day=day,
                shift_id=shift_id,
                machine_id=machine_id,
                available_hours=available_hours,
                sample_id=sample_id,
            )

    for record in records:
        key = (record.day, record.shift_id, record.machine_id)
        summary = aggregates.get(key)
        if summary is None:
            summary = ShiftSummary(
                day=record.day,
                shift_id=record.shift_id,
                machine_id=record.machine_id,
                available_hours=availability_map.get(key, 0.0),
                machine_role=record.machine_role,
                sample_id=sample_id,
            )
            aggregates[key] = summary
        seen.add(key)
        if summary.machine_role is None and record.machine_role is not None:
            summary.machine_role = record.machine_role

        if record.hours_worked is not None:
            summary.total_hours += record.hours_worked
        if record.production_units is not None:
            summary.production_units += record.production_units
        if record.mobilisation_cost is not None:
            summary.mobilisation_cost += record.mobilisation_cost
        if record.blackout_hit:
            summary.blackout_conflicts += 1
        if record.metadata.get("sequencing_violation"):
            summary.sequencing_violations += 1
        if record.downtime and record.hours_worked is not None:
            summary.downtime_hours += record.hours_worked
            summary.downtime_events += 1
        if record.weather_severity:
            summary.weather_severity_total += float(record.weather_severity)

    for key, summary in aggregates.items():
        if summary.idle_hours is None:
            summary.idle_hours = max(summary.available_hours - summary.total_hours, 0.0)
        if summary.available_hours > 0:
            summary.utilisation_ratio = summary.total_hours / summary.available_hours
        else:
            summary.utilisation_ratio = None

    for key in sorted(aggregates):
        if include_idle or key in seen:
            yield aggregates[key]


def summarise_days(
    shift_summaries: Iterable[ShiftSummary],
    availability_map: dict[tuple[int, str, str], float],
    completed_by_day: dict[int, set[str]],
    sample_id: int = 0,
) -> Iterator[DaySummary]:
    """Aggregate playback results to day-level summaries.

    Parameters
    ----------
    shift_summaries:
        Iterable produced by :func:`summarise_shifts`.
    availability_map:
        Same map passed to ``summarise_shifts``; used to recover day-level availability totals.
    completed_by_day:
        Mapping ``day -> set(block_id)`` indicating which blocks completed on each day (consumed for
        KPI reporting).
    sample_id:
        Propagated through stochastic playback.
    """

    aggregates: dict[int, DaySummary] = {}

    availability_by_day: dict[int, float] = defaultdict(float)
    for (day, _shift_id, _machine_id), hours in availability_map.items():
        availability_by_day[day] += hours

    for summary in shift_summaries:
        day_summary = aggregates.get(summary.day)
        if day_summary is None:
            day_summary = DaySummary(day=summary.day, sample_id=sample_id)
            aggregates[summary.day] = day_summary

        day_summary.available_hours += summary.available_hours
        day_summary.total_hours += summary.total_hours
        day_summary.production_units += summary.production_units
        day_summary.mobilisation_cost += summary.mobilisation_cost
        day_summary.blackout_conflicts += summary.blackout_conflicts
        day_summary.sequencing_violations += summary.sequencing_violations
        day_summary.downtime_hours += summary.downtime_hours
        day_summary.downtime_events += summary.downtime_events
        day_summary.weather_severity_total += summary.weather_severity_total

    for day, available in availability_by_day.items():
        day_summary = aggregates.setdefault(day, DaySummary(day=day, sample_id=sample_id))
        day_summary.available_hours = max(day_summary.available_hours, available)

    # Compute per-day idle hours and completed block counts via aggregated data.
    for day in sorted(aggregates):
        day_summary = aggregates[day]
        day_summary.idle_hours = max(day_summary.available_hours - day_summary.total_hours, 0.0)
        day_summary.completed_blocks = len(completed_by_day.get(day, set()))
        if day_summary.available_hours > 0:
            day_summary.utilisation_ratio = day_summary.total_hours / day_summary.available_hours
        else:
            day_summary.utilisation_ratio = None
        yield day_summary


def _compute_shift_availability(
    problem: Problem,
    config: PlaybackConfig,
) -> dict[tuple[int, str, str], float]:
    """Derive available hours per machine/day/shift from scenario data."""

    scenario = problem.scenario
    machines = {machine.id: machine for machine in scenario.machines}

    day_availability: dict[tuple[str, int], int] = {}
    for calendar_entry in scenario.calendar:
        day_availability[(calendar_entry.machine_id, calendar_entry.day)] = calendar_entry.available

    shift_hours = {}
    if scenario.timeline and scenario.timeline.shifts:
        shift_hours = {shift_def.name: shift_def.hours for shift_def in scenario.timeline.shifts}

    availability: dict[tuple[int, str, str], float] = {}

    def machine_available(machine_id: str, day: int) -> bool:
        return day_availability.get((machine_id, day), 1) == 1

    if scenario.shift_calendar:
        for shift_entry in scenario.shift_calendar:
            if shift_entry.available != 1:
                continue
            if shift_entry.machine_id not in machines:
                continue
            if not machine_available(shift_entry.machine_id, shift_entry.day):
                continue
            hours = shift_hours.get(shift_entry.shift_id)
            if hours is None and config.infer_missing_shifts:
                hours = machines[shift_entry.machine_id].daily_hours
            if hours is None:
                continue
            availability[(shift_entry.day, shift_entry.shift_id, shift_entry.machine_id)] = hours
    elif shift_hours:
        for day in problem.days:
            for shift_id, hours in shift_hours.items():
                for machine_id in machines:
                    if not machine_available(machine_id, day):
                        continue
                    availability[(day, shift_id, machine_id)] = hours
    else:
        for day in problem.days:
            for machine_id, machine in machines.items():
                if not machine_available(machine_id, day):
                    continue
                availability[(day, "S1", machine_id)] = machine.daily_hours

    return availability
