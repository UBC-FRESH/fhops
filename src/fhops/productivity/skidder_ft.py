"""Grapple skidder productivity helpers (Han 2018 + Advantage regressions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
import json
import math


class Han2018SkidderMethod(str, Enum):
    """Harvesting method definitions from Han et al. (2018)."""

    LOP_AND_SCATTER = "lop_and_scatter"
    WHOLE_TREE = "whole_tree"


class TrailSpacingPattern(str, Enum):
    """Trail-network layouts from FPInnovations TN285 (ghost-trail study)."""

    NARROW_13_15M = "narrow_13_15m"
    SINGLE_GHOST_18M = "single_ghost_18m"
    DOUBLE_GHOST_27M = "double_ghost_27m"


class DeckingCondition(str, Enum):
    """Decking/landing preparation states from ADV4N21 (loader-forward vs. skidder)."""

    CONSTRAINED = "constrained_decking"
    PREPARED = "prepared_decking"


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


@dataclass(frozen=True)
class SkidderSpeedProfile:
    key: str
    description: str
    empty_speed_kmh: float
    loaded_speed_kmh: float
    notes: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_skidder_speed_profiles() -> dict[str, dict[str, object]]:
    try:
        data = json.loads(_SKIDDER_SPEED_PROFILE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Skidder speed profile data missing: {_SKIDDER_SPEED_PROFILE_PATH}"
        ) from exc
    return (data or {}).get("events") or {}


def get_skidder_speed_profile(key: str) -> SkidderSpeedProfile:
    payload = _load_skidder_speed_profiles().get(key)
    if payload is None:
        valid = ", ".join(sorted(_load_skidder_speed_profiles()))
        raise ValueError(f"Unknown skidder speed profile '{key}'. Valid: {valid}")
    description = "GNSS-derived speed profile"
    if key == "SK":
        description = "GNSS cable skidder median speeds (Zurita & Borz 2025)"
    elif key == "FT":
        description = "GNSS farm-tractor skidder median speeds (Zurita & Borz 2025)"
    notes_payload = payload.get("notes") if isinstance(payload.get("notes"), list) else []
    notes = tuple(str(n) for n in notes_payload)
    return SkidderSpeedProfile(
        key=key,
        description=description,
        empty_speed_kmh=float((payload.get("drive_empty_forest_road") or {}).get("median_kmh")),
        loaded_speed_kmh=float((payload.get("drive_loaded_forest_road") or {}).get("median_kmh")),
        notes=notes,
    )


_TRAIL_PATTERN_INFO: dict[TrailSpacingPattern, dict[str, float | str]] = {
    TrailSpacingPattern.NARROW_13_15M: {
        "multiplier": 0.75,
        "reference": "FPInnovations TN285 (trail spacings 13–15 m raised extraction costs 20–40%).",
    },
    TrailSpacingPattern.SINGLE_GHOST_18M: {
        "multiplier": 0.9,
        "reference": "FPInnovations TN285 (18 m spacing with one ghost trail showed modest load penalties).",
    },
    TrailSpacingPattern.DOUBLE_GHOST_27M: {
        "multiplier": 1.0,
        "reference": "FPInnovations TN285 (27–30 m spacing with two ghost trails baseline).",
    },
}

_DECKING_INFO: dict[DeckingCondition, dict[str, float | str]] = {
    DeckingCondition.CONSTRAINED: {
        "multiplier": 0.84,
        "reference": "FPInnovations ADV4N21 (decking time 1.33 vs. 0.60 min/cycle added ~16% cycle penalty).",
    },
    DeckingCondition.PREPARED: {
        "multiplier": 1.0,
        "reference": "FPInnovations ADV4N21 (decking area cleared prior to skidding).",
    },
}


def _han2018_cycle_time_seconds(
    *,
    method: Han2018SkidderMethod,
    pieces_per_cycle: float,
    empty_distance_m: float,
    loaded_distance_m: float,
    speed_profile: SkidderSpeedProfile | None = None,
) -> float:
    if pieces_per_cycle <= 0:
        raise ValueError("pieces_per_cycle must be > 0")
    if empty_distance_m < 0 or loaded_distance_m < 0:
        raise ValueError("Skidding distances must be >= 0")

    def _segment_time(
        distance_m: float,
        coefficient_seconds_per_m: float,
        profile_speed_kmh: float | None,
    ) -> float:
        if distance_m <= 0:
            return 0.0
        if profile_speed_kmh and profile_speed_kmh > 0:
            speed_m_per_s = profile_speed_kmh * (1000.0 / 3600.0)
            if speed_m_per_s > 0:
                return distance_m / speed_m_per_s
        return coefficient_seconds_per_m * distance_m

    if method is Han2018SkidderMethod.LOP_AND_SCATTER:
        # Delay-free seconds per cycle regression from Table 6.
        return (
            71.779
            + (3.033 * pieces_per_cycle)
            + _segment_time(
                empty_distance_m,
                0.493,
                speed_profile.empty_speed_kmh if speed_profile else None,
            )
            + _segment_time(
                loaded_distance_m,
                0.053,
                speed_profile.loaded_speed_kmh if speed_profile else None,
            )
        )

    return (
        25.125
        + (1.881 * pieces_per_cycle)
        + _segment_time(
            empty_distance_m,
            0.632,
            speed_profile.empty_speed_kmh if speed_profile else None,
        )
        + _segment_time(
            loaded_distance_m,
            0.477,
            speed_profile.loaded_speed_kmh if speed_profile else None,
        )
    )


def estimate_grapple_skidder_productivity_han2018(
    *,
    method: Han2018SkidderMethod,
    pieces_per_cycle: float,
    piece_volume_m3: float,
    empty_distance_m: float,
    loaded_distance_m: float,
    trail_pattern: TrailSpacingPattern | None = None,
    decking_condition: DeckingCondition | None = None,
    custom_multiplier: float | None = None,
    speed_profile: SkidderSpeedProfile | None = None,
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
        speed_profile=speed_profile,
    )
    if cycle_time_seconds <= 0:
        raise ValueError("Derived cycle time must be > 0")

    payload_m3 = pieces_per_cycle * piece_volume_m3
    if payload_m3 <= 0:
        raise ValueError("payload_m3 must be > 0")

    cycles_per_hour = 3600.0 / cycle_time_seconds
    productivity = cycles_per_hour * payload_m3

    applied_multiplier = 1.0
    parameters: dict[str, float | str] = {
        "method": method.value,
        "pieces_per_cycle": pieces_per_cycle,
        "piece_volume_m3": piece_volume_m3,
        "empty_distance_m": empty_distance_m,
        "loaded_distance_m": loaded_distance_m,
    }
    if speed_profile is not None:
        parameters["speed_profile"] = speed_profile.key
        parameters["speed_profile_description"] = speed_profile.description

    if trail_pattern is not None:
        info = _TRAIL_PATTERN_INFO[trail_pattern]
        applied_multiplier *= float(info["multiplier"])
        parameters["trail_pattern"] = trail_pattern.value
        parameters["trail_pattern_multiplier"] = info["multiplier"]
        parameters["trail_pattern_reference"] = info["reference"]

    if decking_condition is not None:
        info = _DECKING_INFO[decking_condition]
        applied_multiplier *= float(info["multiplier"])
        parameters["decking_condition"] = decking_condition.value
        parameters["decking_multiplier"] = info["multiplier"]
        parameters["decking_reference"] = info["reference"]

    if custom_multiplier is not None:
        if custom_multiplier <= 0:
            raise ValueError("custom_multiplier must be > 0")
        applied_multiplier *= custom_multiplier
        parameters["custom_multiplier"] = custom_multiplier

    productivity *= applied_multiplier
    parameters["applied_multiplier"] = applied_multiplier

    return SkidderProductivityResult(
        method=method,
        cycle_time_seconds=cycle_time_seconds,
        payload_m3=payload_m3,
        predicted_m3_per_pmh=productivity,
        parameters=parameters,
    )


def estimate_cable_skidder_productivity_adv1n12_full_tree(
    extraction_distance_m: float,
) -> float:
    """Return m³/PMH for the semi-mechanized full-tree system (lop-and-scatter integrated with skidding).

    Regression derived from FPInnovations Advantage Vol. 1 No. 12 Appendix 2:
        P = 5.4834 · e^(−0.0013·d)
    where ``d`` is the average extraction distance (m).
    """

    if extraction_distance_m <= 0:
        raise ValueError("extraction_distance_m must be > 0")
    return 5.4834 * math.exp(-0.0013 * extraction_distance_m)


def estimate_cable_skidder_productivity_adv1n12_two_phase(
    extraction_distance_m: float,
) -> float:
    """Return m³/PMH for the second-phase extraction skidder in the two-phase system.

    Regression from Advantage Vol. 1 No. 12:
        P = -4.9339 · ln(d) + 35.202
    ``d`` = average extraction distance (m). Only valid for d > 0.
    """

    if extraction_distance_m <= 0:
        raise ValueError("extraction_distance_m must be > 0")
    return -4.9339 * math.log(extraction_distance_m) + 35.202


__all__ = [
    "Han2018SkidderMethod",
    "TrailSpacingPattern",
    "DeckingCondition",
    "SkidderProductivityResult",
    "SkidderSpeedProfile",
    "estimate_grapple_skidder_productivity_han2018",
    "get_skidder_speed_profile",
    "estimate_cable_skidder_productivity_adv1n12_full_tree",
    "estimate_cable_skidder_productivity_adv1n12_two_phase",
]
_SKIDDER_SPEED_PROFILE_PATH = Path(__file__).resolve().parents[3] / "data" / "reference" / "skidder_speed_zurita2025.json"
