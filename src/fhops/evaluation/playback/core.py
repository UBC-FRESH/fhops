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
    total_hours: float = 0.0
    production_units: float = 0.0
    mobilisation_cost: float = 0.0
    completed_blocks: int = 0
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

    from .adapters import assignments_to_records  # Local import to avoid circular dependency.

    cfg = config or PlaybackConfig()
    record_iter = assignments_to_records(problem, assignments)

    # Materialise records since downstream summaries iterate multiple times.
    records: tuple[PlaybackRecord, ...] = tuple(record_iter)

    shift_summaries = tuple(summarise_shifts(records))
    day_summaries = tuple(summarise_days(records))

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


def summarise_shifts(records: Iterable[PlaybackRecord]) -> Iterator[ShiftSummary]:
    """Aggregate playback records to machine/shift summaries."""

    aggregates: dict[tuple[int, str, str], ShiftSummary] = {}
    for record in records:
        key = (record.day, record.shift_id, record.machine_id)
        summary = aggregates.get(key)
        if summary is None:
            summary = ShiftSummary(day=record.day, shift_id=record.shift_id, machine_id=record.machine_id)
            aggregates[key] = summary

        if record.hours_worked is not None:
            summary.total_hours += record.hours_worked
        if record.production_units is not None:
            summary.production_units += record.production_units
        if record.mobilisation_cost is not None:
            summary.mobilisation_cost += record.mobilisation_cost
        if record.blackout_hit:
            summary.blackout_conflicts += 1
        # TODO: populate sequencing violations once playback encodes them.

    for key in sorted(aggregates):
        yield aggregates[key]


def summarise_days(records: Iterable[PlaybackRecord]) -> Iterator[DaySummary]:
    """Aggregate playback records to day-level summaries."""

    aggregates: dict[int, DaySummary] = {}
    completed_by_day: dict[int, set[str]] = defaultdict(set)

    for record in records:
        summary = aggregates.get(record.day)
        if summary is None:
            summary = DaySummary(day=record.day)
            aggregates[record.day] = summary

        if record.hours_worked is not None:
            summary.total_hours += record.hours_worked
        if record.production_units is not None:
            summary.production_units += record.production_units
        if record.mobilisation_cost is not None:
            summary.mobilisation_cost += record.mobilisation_cost
        if record.blackout_hit:
            summary.blackout_conflicts += 1

        if record.block_id and record.metadata.get("block_completed"):
            completed_by_day[record.day].add(record.block_id)

        # TODO: sequencing violation tracking to feed summary.sequencing_violations.

    for day in sorted(aggregates):
        summary = aggregates[day]
        summary.completed_blocks = len(completed_by_day.get(day, set()))
        yield summary
