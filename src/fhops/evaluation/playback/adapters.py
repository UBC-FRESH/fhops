"""Helpers to translate solver outputs into playback records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Iterator

from fhops.scenario.contract import Problem

from .core import PlaybackRecord

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from pandas import DataFrame

    try:
        from fhops.solve.heuristics.sa import Schedule
    except ImportError:  # pragma: no cover - optional dependency during typing
        Schedule = object  # type: ignore[assignment]

__all__ = [
    "schedule_to_records",
    "assignments_to_records",
]


def schedule_to_records(problem: Problem, schedule: "Schedule") -> Iterator[PlaybackRecord]:
    """Convert a heuristic `Schedule` plan into playback records."""

    raise NotImplementedError("Schedule → playback record adapter not yet implemented.")


def assignments_to_records(problem: Problem, assignments: "DataFrame") -> Iterator[PlaybackRecord]:
    """Convert solver assignments dataframe into playback records."""

    raise NotImplementedError("Assignments → playback record adapter not yet implemented.")
