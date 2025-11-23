"""Skidder-harvester productivity models from Stoilov et al. (2021)."""

from __future__ import annotations


def _clip_non_negative(value: float) -> float:
    """Clamp regression output to zero so productivity never returns negative values."""
    return value if value > 0 else 0.0


def estimate_skidder_harvester_productivity_delay_free(
    skidding_distance_m: float,
    trees_per_cycle: float,
) -> float:
    """Delay-free productivity (m^3/PMH) from equation (3)."""

    if skidding_distance_m < 0:
        raise ValueError("skidding_distance_m must be >= 0")
    if trees_per_cycle <= 0:
        raise ValueError("trees_per_cycle must be > 0")

    productivity = 14.59 - 0.018 * skidding_distance_m - 2.16 * trees_per_cycle
    return _clip_non_negative(productivity)


def estimate_skidder_harvester_productivity_with_delays(skidding_distance_m: float) -> float:
    """Productivity including delays (m^3/SMH) from equation (4)."""

    if skidding_distance_m < 0:
        raise ValueError("skidding_distance_m must be >= 0")

    productivity = 12.21 - 0.029 * skidding_distance_m
    return _clip_non_negative(productivity)


__all__ = [
    "estimate_skidder_harvester_productivity_delay_free",
    "estimate_skidder_harvester_productivity_with_delays",
]
