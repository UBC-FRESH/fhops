"""Shift-level scheduling primitives (draft)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class ShiftDefinition:
    """Defines a shift length and count for a machine/job context."""

    name: str
    hours: float
    shifts_per_day: int

    def daily_hours(self) -> float:
        return self.hours * self.shifts_per_day


@dataclass(slots=True)
class BlackoutWindow:
    """Represents a continuous period where work is disallowed."""

    start_day: int
    end_day: int
    reason: str | None = None

    def contains(self, day: int) -> bool:
        return self.start_day <= day <= self.end_day


@dataclass(slots=True)
class TimelineConfig:
    """Aggregates shift definitions and blackout rules for a scenario."""

    shifts: tuple[ShiftDefinition, ...]
    blackouts: tuple[BlackoutWindow, ...] = ()
    days_per_week: int = 7

    def iter_blackouts(self) -> Iterable[BlackoutWindow]:
        return iter(self.blackouts)


__all__ = [
    "ShiftDefinition",
    "BlackoutWindow",
    "TimelineConfig",
]
