"""Helpers for Lahrsen (2025) BC feller-buncher productivity models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from fhops.core.errors import FHOPSValueError


class LahrsenModel(str, Enum):
    """Available coefficient sets from Lahrsen (2025)."""

    DAILY = "daily"
    CUTBLOCK = "cutblock"
    CUTBLOCK_HETEROSCEDASTIC = "cutblock_hetero"


@dataclass(frozen=True)
class ProductivityEstimate:
    """Result of a Lahrsen (2025) productivity prediction."""

    model: LahrsenModel
    avg_stem_size: float
    volume_per_ha: float
    stem_density: float
    ground_slope: float
    predicted_m3_per_pmh: float


@dataclass(frozen=True)
class _Coefficients:
    stem_size: float
    volume_per_ha: float
    stem_density: float
    ground_slope: float
    intercept: float = 0.0


_COEFFICIENTS: Mapping[LahrsenModel, _Coefficients] = {
    LahrsenModel.DAILY: _Coefficients(
        stem_size=67.99345,
        volume_per_ha=0.05943,
        stem_density=0.01236,
        ground_slope=-0.46146,
    ),
    LahrsenModel.CUTBLOCK: _Coefficients(
        stem_size=61.02,
        volume_per_ha=0.052,
        stem_density=0.014,
        ground_slope=-0.24,
    ),
    LahrsenModel.CUTBLOCK_HETEROSCEDASTIC: _Coefficients(
        stem_size=57.08,
        volume_per_ha=0.031,
        stem_density=0.003,
        ground_slope=-0.36,
        intercept=0.013,  # captures block-size effect when set to zero.
    ),
}

# Observed ranges from Lahrsen (2025) daily machine-level dataset (min/max).
_STEM_SIZE_RANGE = (0.09, 1.32)
_VOLUME_HA_RANGE = (75.0, 856.2)
_DENSITY_RANGE = (205.0, 3044.0)
_SLOPE_RANGE = (1.5, 48.9)


def _validate(value: float, name: str, bounds: tuple[float, float]) -> None:
    lo, hi = bounds
    if value <= 0:
        raise FHOPSValueError(f"{name} must be positive (got {value}).")
    if not (lo <= value <= hi):
        # Outside observed range, warn by raising to caller? Instead raise informative error.
        raise FHOPSValueError(
            f"{name}={value} outside Lahrsen (2025) observed range [{lo}, {hi}]."
        )


def estimate_productivity(
    *,
    avg_stem_size: float,
    volume_per_ha: float,
    stem_density: float,
    ground_slope: float,
    model: LahrsenModel = LahrsenModel.DAILY,
    validate_ranges: bool = True,
) -> ProductivityEstimate:
    """Estimate productivity (m³/PMH15) using Lahrsen (2025) coefficients.

    Parameters
    ----------
    avg_stem_size:
        Mean harvested stem size (m³/stem).
    volume_per_ha:
        Mean harvested volume per hectare (m³/ha).
    stem_density:
        Mean harvested stem density (trees/ha).
    ground_slope:
        Average ground slope (%).
    model:
        Which Lahrsen coefficient set to use (daily machine-level by default).
    validate_ranges:
        Whether to enforce observed BC ranges (recommended when working with
        real operations rather than synthetic experiments).
    """

    if validate_ranges:
        _validate(avg_stem_size, "avg_stem_size", _STEM_SIZE_RANGE)
        _validate(volume_per_ha, "volume_per_ha", _VOLUME_HA_RANGE)
        _validate(stem_density, "stem_density", _DENSITY_RANGE)
        _validate(ground_slope, "ground_slope", _SLOPE_RANGE)

    coeffs = _COEFFICIENTS[model]
    predicted = (
        coeffs.intercept
        + coeffs.stem_size * avg_stem_size
        + coeffs.volume_per_ha * volume_per_ha
        + coeffs.stem_density * stem_density
        + coeffs.ground_slope * ground_slope
    )

    return ProductivityEstimate(
        model=model,
        avg_stem_size=avg_stem_size,
        volume_per_ha=volume_per_ha,
        stem_density=stem_density,
        ground_slope=ground_slope,
        predicted_m3_per_pmh=predicted,
    )
