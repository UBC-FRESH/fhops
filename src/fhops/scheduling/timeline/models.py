"""Shift-level scheduling primitives."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ValidationInfo, field_validator

__all__ = ["ShiftDefinition", "BlackoutWindow", "TimelineConfig"]


class ShiftDefinition(BaseModel):
    """Defines a shift length and count for a machine/job context."""

    name: str
    hours: float
    shifts_per_day: int

    @field_validator("hours")
    @classmethod
    def _hours_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("hours must be positive")
        return value

    @field_validator("shifts_per_day")
    @classmethod
    def _shifts_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("shifts_per_day must be positive")
        return value

    def daily_hours(self) -> float:
        return self.hours * self.shifts_per_day


class BlackoutWindow(BaseModel):
    """Represents a continuous period where work is disallowed."""

    start_day: int
    end_day: int
    reason: str | None = None

    @field_validator("end_day")
    @classmethod
    def _end_not_before_start(cls, value: int, info: ValidationInfo) -> int:
        start_day = info.data.get("start_day", value)
        if value < start_day:
            raise ValueError("end_day must be >= start_day")
        return value

    def contains(self, day: int) -> bool:
        return self.start_day <= day <= self.end_day


class TimelineConfig(BaseModel):
    """Aggregates shift definitions and blackout rules for a scenario."""

    shifts: list[ShiftDefinition]
    blackouts: list[BlackoutWindow] = []
    days_per_week: int = 7

    @field_validator("days_per_week")
    @classmethod
    def _days_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("days_per_week must be positive")
        return value

    def iter_blackouts(self) -> Iterable[BlackoutWindow]:
        return iter(self.blackouts)
