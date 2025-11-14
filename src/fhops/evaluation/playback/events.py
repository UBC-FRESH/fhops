"""Configuration schemas for stochastic playback events."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "SamplingEventConfig",
    "DowntimeEventConfig",
    "WeatherEventConfig",
    "LandingShockConfig",
    "SamplingConfig",
]


def _default_downtime_config() -> DowntimeEventConfig:
    return DowntimeEventConfig(
        probability=0.15,
        mean_duration_hours=4.0,
        std_duration_hours=1.5,
    )


def _default_weather_config() -> WeatherEventConfig:
    return WeatherEventConfig(
        day_probability=0.2,
        impact_window_days=1,
        severity_levels={"light": 0.1, "moderate": 0.3, "severe": 0.6},
    )


def _default_landing_config() -> LandingShockConfig:
    return LandingShockConfig(
        probability=0.1,
        capacity_multiplier_range=(0.4, 0.8),
        duration_days=1,
    )


class SamplingEventConfig(BaseModel):
    """Base configuration shared by all stochastic events."""

    enabled: bool = True
    seed_offset: int = 0


class DowntimeEventConfig(SamplingEventConfig):
    """Describes downtime sampling parameters for machines."""

    probability: float = Field(0.15, ge=0.0, le=1.0)
    mean_duration_hours: float = Field(4.0, ge=0.0)
    std_duration_hours: float = Field(1.5, ge=0.0)
    max_concurrent: int | None = None
    target_machine_roles: list[str] | None = None

    @field_validator("max_concurrent")
    @classmethod
    def _validate_max_concurrent(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("max_concurrent must be positive when provided")
        return value


class WeatherEventConfig(SamplingEventConfig):
    """Captures stochastic weather impacts affecting production rates."""

    day_probability: float = Field(0.2, ge=0.0, le=1.0)
    severity_levels: dict[str, float] = Field(
        default_factory=lambda: {"light": 0.1, "moderate": 0.3, "severe": 0.6}
    )
    correlated_days: bool = True
    impact_window_days: int = Field(1, ge=1)
    affected_shifts: list[str] | None = None


class LandingShockConfig(SamplingEventConfig):
    """Parameterises landing congestion shocks reducing capacity."""

    probability: float = Field(0.1, ge=0.0, le=1.0)
    capacity_multiplier_range: tuple[float, float] = Field((0.4, 0.8))
    duration_days: int = Field(1, ge=1)
    target_landing_ids: list[str] | None = None

    @field_validator("capacity_multiplier_range")
    @classmethod
    def _validate_multiplier_range(cls, value: tuple[float, float]) -> tuple[float, float]:
        lower, upper = value
        if lower <= 0 or upper <= 0:
            raise ValueError("capacity multipliers must be positive")
        if lower > upper:
            raise ValueError("capacity multiplier range must be ascending")
        return value


class SamplingConfig(BaseModel):
    """Top-level configuration for stochastic playback ensembles."""

    samples: int = Field(10, ge=1)
    base_seed: int = 123
    downtime: DowntimeEventConfig = Field(default_factory=_default_downtime_config)
    weather: WeatherEventConfig = Field(default_factory=_default_weather_config)
    landing: LandingShockConfig = Field(default_factory=_default_landing_config)
