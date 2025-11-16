"""Forwarder productivity helpers based on Ghaffariyan et al. (2019)."""

from __future__ import annotations

import math


def _validate_inputs(extraction_distance_m: float, slope_factor: float) -> None:
    if extraction_distance_m <= 0:
        raise ValueError("extraction_distance_m must be > 0")
    if slope_factor <= 0:
        raise ValueError("slope_factor must be > 0")


def estimate_forwarder_productivity_small_forwarder_thinning(
    extraction_distance_m: float,
    *,
    slope_factor: float = 1.0,
) -> float:
    """Estimate productivity (m^3/PMH0) for a 14 t forwarder in thinning operations.

    Implements Equation 2 from Ghaffariyan et al. (2019) where productivity is a log-linear
    function of forwarding distance for gentle slopes (<10%). An optional ``slope_factor``
    allows the caller to apply the paper's slope penalties (e.g., multiply by 0.75 for 10–20%
    slopes or 0.15 if following the literal “drops by 85%” statement).
    """

    _validate_inputs(extraction_distance_m, slope_factor)

    base_productivity = 44.32 - 2.72 * math.log(extraction_distance_m)
    productivity = base_productivity * slope_factor
    if productivity <= 0:
        raise ValueError("derived productivity must be > 0")
    return productivity


def estimate_forwarder_productivity_large_forwarder_thinning(
    extraction_distance_m: float,
    *,
    slope_factor: float = 1.0,
) -> float:
    """Estimate productivity (m^3/PMH0) for a 20 t forwarder in thinning operations.

    Implements Equation 3 from Ghaffariyan et al. (2019). ``slope_factor`` lets callers apply
    slope adjustments beyond the <10% baseline captured by the regression.
    """

    _validate_inputs(extraction_distance_m, slope_factor)

    base_productivity = 87.65 / (extraction_distance_m ** 0.126)
    productivity = base_productivity * slope_factor
    if productivity <= 0:
        raise ValueError("derived productivity must be > 0")
    return productivity


__all__ = [
    "estimate_forwarder_productivity_small_forwarder_thinning",
    "estimate_forwarder_productivity_large_forwarder_thinning",
]
