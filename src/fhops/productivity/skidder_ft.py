"""Grapple skidder productivity helpers (Han et al. 2018)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Han2018SkidderMethod(str, Enum):
    """Harvesting method definitions from Han et al. (2018)."""

    LOP_AND_SCATTER = "lop_and_scatter"
    WHOLE_TREE = "whole_tree"


@dataclass(frozen=True)
class SkidderProductivityResult:
    """Payload returned by the grapple skidder helper."""

    method: Han2018SkidderMethod
    cycle_time_seconds: float
    payload_m3: float
    predicted_m3_per_pmh: float
    pmh_basis: str = "PMH0"
    reference: str = "Han et al. 2018"
    parameters: dict[str, float | str] = field(default_factory=dict)


def _han2018_cycle_time_seconds(
    *,
    method: Han2018SkidderMethod,
    pieces_per_cycle: float,
    empty_distance_m: float,
    loaded_distance_m: float,
) -> float:
    if pieces_per_cycle <= 0:
        raise ValueError("pieces_per_cycle must be > 0")
    if empty_distance_m < 0 or loaded_distance_m < 0:
        raise ValueError("Skidding distances must be >= 0")

    if method is Han2018SkidderMethod.LOP_AND_SCATTER:
        # Delay-free seconds per cycle regression from Table 6.
        return (
            71.779
            + (3.033 * pieces_per_cycle)
            + (0.493 * empty_distance_m)
            + (0.053 * loaded_distance_m)
        )

    return (
        25.125
        + (1.881 * pieces_per_cycle)
        + (0.632 * empty_distance_m)
        + (0.477 * loaded_distance_m)
    )


def estimate_grapple_skidder_productivity_han2018(
    *,
    method: Han2018SkidderMethod,
    pieces_per_cycle: float,
    piece_volume_m3: float,
    empty_distance_m: float,
    loaded_distance_m: float,
) -> SkidderProductivityResult:
    """Estimate grapple-skidder productivity (m³/PMH0).

    ``pieces_per_cycle`` is interpreted as log count under lop-and-scatter and tree count under
    whole-tree harvesting. ``piece_volume_m3`` should already reflect bucked log or whole-tree
    volume in cubic metres.
    """

    if piece_volume_m3 <= 0:
        raise ValueError("piece_volume_m3 must be > 0")

    cycle_time_seconds = _han2018_cycle_time_seconds(
        method=method,
        pieces_per_cycle=pieces_per_cycle,
        empty_distance_m=empty_distance_m,
        loaded_distance_m=loaded_distance_m,
    )
    if cycle_time_seconds <= 0:
        raise ValueError("Derived cycle time must be > 0")

    payload_m3 = pieces_per_cycle * piece_volume_m3
    if payload_m3 <= 0:
        raise ValueError("payload_m3 must be > 0")

    cycles_per_hour = 3600.0 / cycle_time_seconds
    productivity = cycles_per_hour * payload_m3

    parameters: dict[str, float | str] = {
        "method": method.value,
        "pieces_per_cycle": pieces_per_cycle,
        "piece_volume_m3": piece_volume_m3,
        "empty_distance_m": empty_distance_m,
        "loaded_distance_m": loaded_distance_m,
    }

    return SkidderProductivityResult(
        method=method,
        cycle_time_seconds=cycle_time_seconds,
        payload_m3=payload_m3,
        predicted_m3_per_pmh=productivity,
        parameters=parameters,
    )


__all__ = [
    "Han2018SkidderMethod",
    "SkidderProductivityResult",
    "estimate_grapple_skidder_productivity_han2018",
]
