"""Evaluation layer (playback, metrics, reporting)."""

from .metrics.kpis import compute_kpis
from .playback import (
    DaySummary,
    DowntimeEventConfig,
    LandingShockConfig,
    PlaybackConfig,
    PlaybackRecord,
    PlaybackResult,
    SamplingConfig,
    SamplingEventConfig,
    ShiftSummary,
    WeatherEventConfig,
    assignments_to_records,
    run_playback,
    schedule_to_records,
    summarise_days,
    summarise_shifts,
)

__all__ = [
    "compute_kpis",
    "PlaybackConfig",
    "PlaybackRecord",
    "PlaybackResult",
    "ShiftSummary",
    "DaySummary",
    "run_playback",
    "summarise_shifts",
    "summarise_days",
    "assignments_to_records",
    "schedule_to_records",
    "SamplingEventConfig",
    "DowntimeEventConfig",
    "WeatherEventConfig",
    "LandingShockConfig",
    "SamplingConfig",
]
