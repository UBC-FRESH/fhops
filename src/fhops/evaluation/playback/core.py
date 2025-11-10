"""Deterministic playback primitives."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Iterator, Sequence

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
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ShiftSummary:
    """Aggregated metrics per machine/shift."""

    day: int
    shift_id: str
    machine_id: str
    available_hours: float = 0.0
    total_hours: float = 0.0
    production_units: float = 0.0
    mobilisation_cost: float = 0.0
    idle_hours: float | None = None
    blackout_conflicts: int = 0
    sequencing_violations: int = 0


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


@dataclass(slots=True)
class PlaybackResult:
    """Container grouping playback outputs."""

    records: Sequence[PlaybackRecord]
    shift_summaries: Sequence[ShiftSummary]
    day_summaries: Sequence[DaySummary]
    config: PlaybackConfig


def run_playback(
    problem: Problem,
    assignments: "pd.DataFrame",
    *,
    config: PlaybackConfig | None = None,
) -> PlaybackResult:
    """Convert solver assignments into playback records and aggregated summaries."""

    cfg = config or PlaybackConfig()
    availability_map = _compute_shift_availability(problem, cfg)

    from .adapters import assignments_to_records  # Local import to avoid circular dependency.

    record_iter = assignments_to_records(problem, assignments)

    # Materialise records since downstream summaries iterate multiple times.
    records: tuple[PlaybackRecord, ...] = tuple(record_iter)

    shift_summaries = tuple(
        summarise_shifts(
            records,
            availability_map,
            include_idle=cfg.include_idle_records,
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
    )


def summarise_shifts(
    records: Iterable[PlaybackRecord],
    availability_map: dict[tuple[int, str, str], float],
    *,
    include_idle: bool = False,
) -> Iterator[ShiftSummary]:
    """Aggregate playback records to machine/shift summaries."""

    aggregates: dict[tuple[int, str, str], ShiftSummary] = {}
    seen: set[tuple[int, str, str]] = set()

    if include_idle:
        for (day, shift_id, machine_id), available_hours in availability_map.items():
            aggregates[(day, shift_id, machine_id)] = ShiftSummary(
                day=day,
                shift_id=shift_id,
                machine_id=machine_id,
                available_hours=available_hours,
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
            )
            aggregates[key] = summary
        seen.add(key)

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

    for key, summary in aggregates.items():
        if summary.idle_hours is None:
            summary.idle_hours = max(summary.available_hours - summary.total_hours, 0.0)

    for key in sorted(aggregates):
        if include_idle or key in seen:
            yield aggregates[key]


def summarise_days(
    shift_summaries: Iterable[ShiftSummary],
    availability_map: dict[tuple[int, str, str], float],
    completed_by_day: dict[int, set[str]],
) -> Iterator[DaySummary]:
    """Aggregate playback results to day-level summaries."""

    aggregates: dict[int, DaySummary] = {}

    availability_by_day: dict[int, float] = defaultdict(float)
    for (day, _shift_id, _machine_id), hours in availability_map.items():
        availability_by_day[day] += hours

    for summary in shift_summaries:
        day_summary = aggregates.get(summary.day)
        if day_summary is None:
            day_summary = DaySummary(day=summary.day)
            aggregates[summary.day] = day_summary

        day_summary.available_hours += summary.available_hours
        day_summary.total_hours += summary.total_hours
        day_summary.production_units += summary.production_units
        day_summary.mobilisation_cost += summary.mobilisation_cost
        day_summary.blackout_conflicts += summary.blackout_conflicts
        day_summary.sequencing_violations += summary.sequencing_violations

    for day, available in availability_by_day.items():
        day_summary = aggregates.setdefault(day, DaySummary(day=day))
        day_summary.available_hours = max(day_summary.available_hours, available)

    # Compute per-day idle hours and completed block counts via aggregated data.
    for day in sorted(aggregates):
        day_summary = aggregates[day]
        day_summary.idle_hours = max(day_summary.available_hours - day_summary.total_hours, 0.0)
        day_summary.completed_blocks = len(completed_by_day.get(day, set()))
        yield day_summary


def _compute_shift_availability(
    problem: Problem,
    config: PlaybackConfig,
) -> dict[tuple[int, str, str], float]:
    """Derive available hours per machine/day/shift from scenario data."""

    scenario = problem.scenario
    machines = {machine.id: machine for machine in scenario.machines}

    day_availability: dict[tuple[str, int], int] = {}
    for entry in scenario.calendar:
        day_availability[(entry.machine_id, entry.day)] = entry.available

    shift_hours = {}
    if scenario.timeline and scenario.timeline.shifts:
        shift_hours = {shift_def.name: shift_def.hours for shift_def in scenario.timeline.shifts}

    availability: dict[tuple[int, str, str], float] = {}

    def machine_available(machine_id: str, day: int) -> bool:
        return day_availability.get((machine_id, day), 1) == 1

    if scenario.shift_calendar:
        for entry in scenario.shift_calendar:
            if entry.available != 1:
                continue
            if entry.machine_id not in machines:
                continue
            if not machine_available(entry.machine_id, entry.day):
                continue
            hours = shift_hours.get(entry.shift_id)
            if hours is None and config.infer_missing_shifts:
                hours = machines[entry.machine_id].daily_hours
            if hours is None:
                continue
            availability[(entry.day, entry.shift_id, entry.machine_id)] = hours
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
