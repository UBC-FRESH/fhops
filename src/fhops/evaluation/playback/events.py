"""Configuration schemas for stochastic playback events.

The models in this module parameterise the stochastic events applied by
:func:`fhops.evaluation.playback.stochastic.run_stochastic_playback` (machine downtime, weather
spells, landing congestion shocks). They are plain Pydantic models so they can be built from
Python, YAML/JSON payloads, or the ``fhops eval-playback`` CLI flags.
"""

from __future__ import annotations

import warnings
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "SamplingEventConfig",
    "DowntimeEventConfig",
    "WeatherEventConfig",
    "LandingShockConfig",
    "SamplingConfig",
]


def _default_downtime_config() -> DowntimeEventConfig:
    """Return the default downtime sampling parameters used by SamplingConfig."""
    return DowntimeEventConfig(
        probability=0.15,
        mean_duration_hours=4.0,
        std_duration_hours=1.5,
    )


def _default_weather_config() -> WeatherEventConfig:
    """Return the default weather-impact configuration (probabilities, severities)."""
    return WeatherEventConfig(
        day_probability=0.2,
        impact_window_days=1,
        severity_levels={"light": 0.1, "moderate": 0.3, "severe": 0.6},
    )


def _default_landing_config() -> LandingShockConfig:
    """Return the default landing shock parameters (probability, duration, multiplier)."""
    return LandingShockConfig(
        probability=0.1,
        capacity_multiplier_range=(0.4, 0.8),
        duration_days=1,
    )


class SamplingEventConfig(BaseModel):
    """Base configuration shared by all stochastic events.

    Parameters
    ----------
    enabled : bool, default=True
        Whether :func:`~fhops.evaluation.playback.stochastic.run_stochastic_playback` applies the
        event when it builds the default event list.
    seed_offset : int, default=0
        **Deprecated** (FHOPS 1.0.1) and ignored: every event of sample ``i`` draws from the
        shared generator ``numpy.random.default_rng(base_seed + i)`` in the order downtime →
        weather → landing shocks (FHOPS 1.0.0 also ignored this field). Setting a non-zero value
        emits a :class:`DeprecationWarning`; ``0`` (e.g. a round trip of a dumped default
        config) does not.
    """

    enabled: bool = True
    seed_offset: int = Field(
        default=0,
        description="Deprecated and ignored; events share the per-sample generator.",
    )

    @model_validator(mode="after")
    def _warn_seed_offset(self) -> Self:
        if "seed_offset" in self.model_fields_set and self.seed_offset != 0:
            warnings.warn(
                f"{type(self).__name__}.seed_offset is deprecated and ignored; every event of a "
                "sample draws from the shared generator default_rng(base_seed + sample_id).",
                DeprecationWarning,
                stacklevel=2,
            )
        return self


class DowntimeEventConfig(SamplingEventConfig):
    """Describes downtime sampling parameters for machines.

    Parameters
    ----------
    probability : float, default=0.15
        Probability in ``[0, 1]`` that an eligible machine-shift assignment is hit by downtime.
        Ignored for selection when ``max_concurrent`` is set (see below); ``0`` disables the event.
    mean_duration_hours : float, default=4.0
        Mean of the Normal distribution used to sample the downtime duration (hours, ``>= 0``).
    std_duration_hours : float, default=1.5
        Standard deviation of the downtime duration (hours, ``>= 0``). ``0`` makes every
        downtime last exactly ``mean_duration_hours`` (clipped to the shift length).
    max_concurrent : int | None, default=None
        When set, exactly ``min(max_concurrent, n)`` of the ``n`` eligible assignments on each
        day are hit, chosen uniformly without replacement; when ``None`` each assignment is hit
        independently with ``probability``. Must be positive when provided.
    target_machine_roles : list[str] | None, default=None
        Restrict downtime to machines whose ``role`` is in this list (``None`` targets all).

    Notes
    -----
    The sampled duration ``d`` is clipped to ``[0, shift_hours]`` and removes the fraction
    ``d / shift_hours`` of the assignment's production. A full-shift loss (``d == shift_hours``)
    cancels the assignment. See :class:`fhops.evaluation.playback.stochastic.DowntimeEvent`.
    """

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
    """Captures stochastic weather impacts affecting production rates.

    Parameters
    ----------
    day_probability : float, default=0.2
        Probability in ``[0, 1]`` that a weather spell starts on a given assignment day.
    severity_levels : dict[str, float]
        Mapping ``label -> severity``; a spell picks one level uniformly at random and scales
        affected production by ``1 - severity`` (severity in ``[0, 1]``).
    correlated_days : bool, default=True
        **Deprecated** (FHOPS 1.0.1) and ignored. Explicitly setting a non-default value
        (``False``) emits a :class:`DeprecationWarning`; the default ``True`` (e.g. a round trip
        of a dumped config or an older synthetic ``metadata.yaml``) does not. Use
        ``impact_window_days`` to model multi-day spells.
    impact_window_days : int, default=1
        Number of consecutive calendar days covered by each spell (``>= 1``); overlapping
        spells keep the highest severity per day.
    affected_shifts : list[str] | None, default=None
        Restrict weather impacts to these shift IDs (``None`` affects every shift).
    """

    day_probability: float = Field(0.2, ge=0.0, le=1.0)
    severity_levels: dict[str, float] = Field(
        default_factory=lambda: {"light": 0.1, "moderate": 0.3, "severe": 0.6}
    )
    correlated_days: bool = Field(
        default=True,
        description=(
            "Deprecated and ignored; use impact_window_days to model multi-day weather spells."
        ),
    )
    impact_window_days: int = Field(1, ge=1)
    affected_shifts: list[str] | None = None

    @model_validator(mode="after")
    def _warn_correlated_days(self) -> Self:
        if "correlated_days" in self.model_fields_set and self.correlated_days is not True:
            warnings.warn(
                "WeatherEventConfig.correlated_days is deprecated and ignored; use "
                "impact_window_days to model multi-day weather spells.",
                DeprecationWarning,
                stacklevel=2,
            )
        return self


class LandingShockConfig(SamplingEventConfig):
    """Parameterises landing congestion shocks reducing capacity.

    Parameters
    ----------
    probability : float, default=0.1
        Probability in ``[0, 1]`` that a shock starts at a landing on a given calendar day of
        the scenario horizon (``0`` disables the event).
    capacity_multiplier_range : tuple[float, float], default=(0.4, 0.8)
        Ascending ``(low, high)`` bounds (both ``> 0``) of the uniform distribution from which
        each shock's production multiplier is drawn.
    duration_days : int, default=1
        Number of consecutive calendar days each shock lasts, starting on its start day
        (``>= 1``).
    target_landing_ids : list[str] | None, default=None
        Restrict shocks to these landings (``None`` uses every scenario landing).

    Notes
    -----
    Every assignment on a block served by a shocked landing has its production scaled by the
    shock multiplier on each affected day; overlapping shocks use the minimum multiplier. See
    :class:`fhops.evaluation.playback.stochastic.LandingShockEvent`.

    Shocks start independently for each landing and calendar day, so the expected fraction of
    landing-days under a shock is ``1 - (1 - probability) ** duration_days`` (days
    ``d < duration_days`` at the start of the horizon use ``d`` instead of ``duration_days``).
    The defaults (``probability=0.1``, ``duration_days=1``) shock 10 % of landing-days, with a
    mean multiplier of ``(low + high) / 2 = 0.6`` on those days.
    """

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
