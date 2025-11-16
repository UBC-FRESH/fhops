"""Forwarder productivity regression from Kellogg & Bettinger (1994)."""

from __future__ import annotations

from enum import Enum


class LoadType(str, Enum):
    """Forwarded product mix in the Kellogg & Bettinger thinning study."""

    SAWLOG = "sawlog"
    PULPWOOD = "pulpwood"
    MIXED = "mixed"


_LOAD_TYPE_OFFSETS = {
    LoadType.SAWLOG: 0.0,
    LoadType.MIXED: -1.689,
    LoadType.PULPWOOD: -3.478,
}


def estimate_forwarder_productivity_kellogg_bettinger(
    *,
    load_type: LoadType,
    volume_per_load_m3: float,
    distance_out_m: float,
    travel_in_unit_m: float,
    distance_in_m: float,
) -> float:
    """Predict forwarder productivity (m^3/PMH) for OR thinning conditions.

    Implements the regression on p.49 of Kellogg & Bettinger (1994) where productivity
    is linear in per-load volume and the distance components for the travel cycle.
    """

    if volume_per_load_m3 <= 0:
        raise ValueError("volume_per_load_m3 must be > 0")
    if distance_out_m < 0 or travel_in_unit_m < 0 or distance_in_m < 0:
        raise ValueError("distance inputs must be >= 0")

    indicator_offset = _LOAD_TYPE_OFFSETS[load_type]

    productivity = (
        16.245
        + indicator_offset
        + 0.2707 * volume_per_load_m3
        - 0.008 * distance_out_m
        - 0.0057 * travel_in_unit_m
        - 0.0039 * distance_in_m
    )

    if productivity <= 0:
        raise ValueError("derived productivity must be > 0")

    return productivity


__all__ = ["LoadType", "estimate_forwarder_productivity_kellogg_bettinger"]
