"""Deterministic playback scaffolding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Iterator, Sequence

from fhops.scenario.contract import Problem

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
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
    include_idle_records: bool = False


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
    total_hours: float | None = None
    production_units: float | None = None
    mobilisation_cost: float | None = None
    idle_hours: float | None = None
    blackout_conflicts: int = 0
    sequencing_violations: int = 0


@dataclass(slots=True)
class DaySummary:
    """Aggregated metrics per day across machines."""

    day: int
    total_hours: float | None = None
    production_units: float | None = None
    mobilisation_cost: float | None = None
    completed_blocks: int | None = None
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
    """Convert solver assignments into playback records and aggregated summaries.

    Parameters
    ----------
    problem:
        Canonical problem description containing scenario/timeline metadata.
    assignments:
        Assignment dataframe (machine ↔ block per day/shift) as produced by solvers.
    config:
        Optional playback configuration toggles.

    Notes
    -----
    This function currently acts as a scaffold and will be implemented in the next
    iteration when deterministic playback logic is migrated from notebooks/tests.
    """

    raise NotImplementedError("Deterministic playback runner not implemented yet.")


def summarise_shifts(records: Iterable[PlaybackRecord]) -> Iterator[ShiftSummary]:
    """Aggregate playback records to machine/shift summaries."""

    raise NotImplementedError("Shift-level summarisation not implemented yet.")


def summarise_days(records: Iterable[PlaybackRecord]) -> Iterator[DaySummary]:
    """Aggregate playback records to day-level summaries."""

    raise NotImplementedError("Day-level summarisation not implemented yet.")
