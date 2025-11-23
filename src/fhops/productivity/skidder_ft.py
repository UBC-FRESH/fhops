"""Grapple skidder productivity helpers (Han 2018 + Advantage regressions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import json
import math
from pathlib import Path


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


class ADV6N7DeckingMode(str, Enum):
    """Decking variants from FPInnovations Advantage Vol. 6 No. 7."""

    SKIDDER = "skidder"
    SKIDDER_LOADER = "skidder_loader"
    LOADER = "loader"
    HOT_PROCESSING = "hot_processing"


@dataclass(frozen=True)
class SkidderProductivityResult:
    """Payload returned by the Han et al. (2018) grapple-skidder helper.

    Attributes
    ----------
    method:
        Harvesting method (lop-and-scatter vs whole-tree) used to select the regression.
    cycle_time_seconds:
        Delay-free cycle time derived from Table 6 (seconds).
    payload_m3:
        Payload per cycle (m³) computed from ``pieces_per_cycle`` and ``piece_volume_m3``.
    predicted_m3_per_pmh:
        Productivity in m³/PMH0 (multipliers applied).
    pmh_basis:
        PMH basis description (defaults to ``"PMH0"``).
    reference:
        Short citation string (defaults to ``"Han et al. 2018"``).
    parameters:
        Echo of the inputs and multipliers used. Helpful for telemetry tables and CLI logs.
    """

    method: Han2018SkidderMethod
    cycle_time_seconds: float
    payload_m3: float
    predicted_m3_per_pmh: float
    pmh_basis: str = "PMH0"
    reference: str = "Han et al. 2018"
    parameters: dict[str, float | str] = field(default_factory=dict)


@dataclass(frozen=True)
class SkidderSpeedProfile:
    """Median travel speeds derived from GNSS traces (Zurita & Borz 2025)."""

    key: str
    description: str
    empty_speed_kmh: float
    loaded_speed_kmh: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ADV6N7Metadata:
    """Static metadata parsed from FPInnovations ADV6N7 JSON."""

    cycle_distance_coeff: float
    cycle_intercepts: dict[ADV6N7DeckingMode, float]
    default_payload_m3: float
    default_utilisation: float
    default_delay_minutes: float
    default_support_ratio: float
    default_skidding_distance_m: float
    skidder_hourly_cost_per_smh_cad_2004: float
    loader_hourly_cost_per_smh_cad_2004: float
    loader_forwarding_cost_per_m3_at_85m_cad_2004: float | None
    distance_range_m: tuple[float, float]
    cost_base_year: int
    note: str


@dataclass(frozen=True)
class ADV6N7SkidderResult:
    """Structured response for the ADV6N7 Caterpillar 535B regression."""

    decking_mode: ADV6N7DeckingMode
    skidding_distance_m: float
    payload_m3: float
    utilisation: float
    delay_minutes: float
    cycle_time_minutes: float
    productivity_m3_per_pmh: float
    skidder_cost_per_m3_cad_2004: float
    combined_cost_per_m3_cad_2004: float | None
    support_ratio: float | None
    metadata: ADV6N7Metadata
    note: str


_ADV6N7_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "reference" / "fpinnovations" / "adv6n7_caterpillar535b.json"
)


@lru_cache(maxsize=1)
def _load_skidder_speed_profiles() -> dict[str, dict[str, object]]:
    """Load GNSS-derived skidder speed profiles for travel-time overrides."""
    try:
        data = json.loads(_SKIDDER_SPEED_PROFILE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Skidder speed profile data missing: {_SKIDDER_SPEED_PROFILE_PATH}"
        ) from exc
    return (data or {}).get("events") or {}


@lru_cache(maxsize=1)
def get_adv6n7_metadata() -> ADV6N7Metadata:
    """Load and cache the ADV6N7 regression metadata from the bundled JSON file."""
    if not _ADV6N7_PATH.exists():
        raise FileNotFoundError(f"ADV6N7 dataset not found: {_ADV6N7_PATH}")
    payload = json.loads(_ADV6N7_PATH.read_text(encoding="utf-8"))
    regressions = payload["regressions"]
    cycle_entries: dict[str, dict[str, object]] = regressions["cycle_time"]["equations"]
    intercepts: dict[ADV6N7DeckingMode, float] = {}
    distance_coeff = None
    mapping = {
        "skidder_only": ADV6N7DeckingMode.SKIDDER,
        "skidder_loader": ADV6N7DeckingMode.SKIDDER_LOADER,
        "loader_only": ADV6N7DeckingMode.LOADER,
        "hot_processing": ADV6N7DeckingMode.HOT_PROCESSING,
    }
    for key, mode in mapping.items():
        entry = cycle_entries.get(key) or {}
        coeffs = entry.get("coefficients") or {}
        intercepts[mode] = float(coeffs.get("intercept", 0.0))
        if distance_coeff is None:
            distance_coeff = float(coeffs.get("distance", 0.0))
    defaults = regressions["productivity"]["defaults"]
    range_payload = regressions["cycle_time"].get("range_m") or [0.0, 0.0]
    costs = payload["costs"]["hourly_components"]
    loader_costs = costs.get("loader_forwarder") or {}
    skidder_costs = costs.get("skidder") or {}
    note = (
        "[dim]Regression from FPInnovations Advantage Vol. 6 No. 7 "
        "(Caterpillar 535B grapple skidder supporting Englewood loader-forwarding).[/dim]"
    )
    return ADV6N7Metadata(
        cycle_distance_coeff=float(distance_coeff or 0.0),
        cycle_intercepts=intercepts,
        default_payload_m3=float(defaults.get("payload_m3", 7.69)),
        default_utilisation=float(defaults.get("utilisation", 0.85)),
        default_delay_minutes=float(defaults.get("delay_minutes", 0.12)),
        default_support_ratio=0.4,
        default_skidding_distance_m=float(defaults.get("skidding_distance_m", 85.0)),
        skidder_hourly_cost_per_smh_cad_2004=float(skidder_costs.get("total_per_smh_cad_2004", 115.21)),
        loader_hourly_cost_per_smh_cad_2004=float(loader_costs.get("total_per_smh_cad_2004", 144.46)),
        loader_forwarding_cost_per_m3_at_85m_cad_2004=float(
            (payload["costs"]["unit_costs"].get("loader_forwarding_per_m3_at_85m_cad_2004") or 0.0)
        )
        or None,
        distance_range_m=(float(range_payload[0]), float(range_payload[1])),
        cost_base_year=2004,
        note=note,
    )


def get_skidder_speed_profile(key: str) -> SkidderSpeedProfile:
    """Return a GNSS-derived skidder speed profile by identifier."""

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


def estimate_grapple_skidder_productivity_adv6n7(
    *,
    skidding_distance_m: float,
    decking_mode: ADV6N7DeckingMode,
    payload_m3: float | None = None,
    utilisation: float | None = None,
    delay_minutes: float | None = None,
    support_ratio: float | None = None,
) -> ADV6N7SkidderResult:
    """Estimate Caterpillar 535B grapple-skidder productivity/costs (ADV6N7).

    Parameters
    ----------
    skidding_distance_m : float
        Corridor distance in metres used in the Advantage regression. Must be positive.
    decking_mode : ADV6N7DeckingMode
        Decking variant (skidder-only, skidder+loader, etc.) which selects the regression intercept.
    payload_m3 : float, optional
        Payload per cycle (m³). Defaults to the study's mean (≈7.7 m³) when omitted.
    utilisation : float, optional
        Utilisation ratio (0–1). Defaults to 0.85 from the report when omitted.
    delay_minutes : float, optional
        Additional minutes per cycle to reflect observed micro-delays (defaults to 0.12 min).
    support_ratio : float, optional
        Fraction (0–1) of cycles assisted by a loader. When provided and ``decking_mode`` is not
        ``SKIDDER``, the helper reports the combined skidder+loader cost per cubic metre.

    Returns
    -------
    ADV6N7SkidderResult
        Dataclass summarising payloads, utilisation, cycle time, m³/PMH, and CPI-aware cost metrics
        (2004 CAD baseline included).

    Notes
    -----
    Based on FPInnovations Advantage Vol. 6 No. 7 (Caterpillar 535B supporting Englewood loader
    forwarding). Costs remain in 2004 CAD—the CLI converts them to current dollars when rendering
    cost tables.
    """

    if skidding_distance_m <= 0:
        raise ValueError("Skidding distance must be > 0")
    metadata = get_adv6n7_metadata()
    payload = metadata.default_payload_m3 if payload_m3 is None else float(payload_m3)
    if payload <= 0:
        raise ValueError("Payload per cycle must be > 0")
    utilised = metadata.default_utilisation if utilisation is None else float(utilisation)
    if utilised <= 0:
        raise ValueError("Utilisation must be > 0")
    delay = metadata.default_delay_minutes if delay_minutes is None else float(delay_minutes)
    if delay < 0:
        raise ValueError("Delay minutes must be >= 0")
    sr = metadata.default_support_ratio if support_ratio is None else float(support_ratio)
    if sr < 0:
        raise ValueError("Support ratio must be >= 0")
    if sr > 1:
        raise ValueError("Support ratio must be <= 1")
    intercept = metadata.cycle_intercepts[decking_mode]
    cycle_minutes = intercept + metadata.cycle_distance_coeff * skidding_distance_m
    if cycle_minutes <= 0:
        raise ValueError("Derived cycle time must be > 0")
    productivity = 60.0 * payload * utilised / (cycle_minutes + delay)
    if productivity <= 0:
        raise ValueError("Derived productivity must be > 0")
    skidder_cost_per_m3 = metadata.skidder_hourly_cost_per_smh_cad_2004 / productivity
    combined_cost: float | None = None
    support_value: float | None = None
    if sr > 0:
        if decking_mode is ADV6N7DeckingMode.SKIDDER:
            raise ValueError("Set --skidder-adv6n7-decking-mode to a supported option when using a support ratio.")
        skidder_only_cycle = metadata.cycle_intercepts[ADV6N7DeckingMode.SKIDDER] + (
            metadata.cycle_distance_coeff * skidding_distance_m
        )
        skidder_only_prod = 60.0 * payload * utilised / (skidder_only_cycle + delay)
        combined_productivity = skidder_only_prod * (1.0 - sr) + productivity * sr
        combined_cost = (
            metadata.skidder_hourly_cost_per_smh_cad_2004
            + metadata.loader_hourly_cost_per_smh_cad_2004 * sr
        ) / combined_productivity
        support_value = sr
    return ADV6N7SkidderResult(
        decking_mode=decking_mode,
        skidding_distance_m=skidding_distance_m,
        payload_m3=payload,
        utilisation=utilised,
        delay_minutes=delay,
        cycle_time_minutes=cycle_minutes,
        productivity_m3_per_pmh=productivity,
        skidder_cost_per_m3_cad_2004=skidder_cost_per_m3,
        combined_cost_per_m3_cad_2004=combined_cost,
        support_ratio=support_value,
        metadata=metadata,
        note=metadata.note,
    )


def _han2018_cycle_time_seconds(
    *,
    method: Han2018SkidderMethod,
    pieces_per_cycle: float,
    empty_distance_m: float,
    loaded_distance_m: float,
    speed_profile: SkidderSpeedProfile | None = None,
) -> float:
    """
    Return delay-free cycle time (seconds) using Han et al. (2018) regressions.

    Parameters
    ----------
    method:
        Harvesting method (`lop_and_scatter` or `whole_tree`).
    pieces_per_cycle:
        Pieces handled per cycle. Must be > 0.
    empty_distance_m, loaded_distance_m:
        Empty/loaded travel distances (m). Must be ≥ 0.
    speed_profile:
        Optional GNSS-derived speed profile used to override the travel coefficients.

    Returns
    -------
    float
        Delay-free cycle time (seconds).
    """
    if pieces_per_cycle <= 0:
        raise ValueError("pieces_per_cycle must be > 0")
    if empty_distance_m < 0 or loaded_distance_m < 0:
        raise ValueError("Skidding distances must be >= 0")

    def _segment_time(
        distance_m: float,
        coefficient_seconds_per_m: float,
        profile_speed_kmh: float | None,
    ) -> float:
        """Return segment time (seconds) using either GNSS speeds or regression coefficients."""
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
    """Estimate grapple-skidder productivity (m³/PMH0) using Han et al. (2018).

    Parameters
    ----------
    method : Han2018SkidderMethod
        Harvesting method (lop-and-scatter or whole-tree). Determines which regression coefficients
        are used and how ``pieces_per_cycle`` is interpreted (logs vs. whole trees).
    pieces_per_cycle : float
        Log or tree count handled per cycle. Must be positive.
    piece_volume_m3 : float
        Average volume per piece (m³). Multiply by ``pieces_per_cycle`` to obtain payload per cycle.
    empty_distance_m : float
        Empty travel distance (metres). Used in the regression's distance terms.
    loaded_distance_m : float
        Loaded travel distance (metres).
    trail_pattern : TrailSpacingPattern, optional
        Applies FPInnovations TN285 multipliers for narrow/ghost-trail spacing layouts.
    decking_condition : DeckingCondition, optional
        Applies ADV4N21 decking penalties when landings are constrained.
    custom_multiplier : float, optional
        User-defined multiplier (``> 0``) applied after the built-in modifiers.
    speed_profile : SkidderSpeedProfile, optional
        GNSS-derived empty/loaded speeds (Zurita & Borz 2025). Overrides regression distance
        coefficients when supplied.

    Returns
    -------
    SkidderProductivityResult
        Dataclass containing cycle time (seconds), payload (m³), PMH basis, and a parameter echo
        detailing which multipliers were applied.

    Notes
    -----
    * ``pieces_per_cycle`` refers to logs for lop-and-scatter and whole trees for whole-tree
      harvesting (matching Han et al. Table 6).
    * Productivity is returned on a delay-free (PMH0) basis, so apply utilisation outside this helper
      if needed.
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
    "ADV6N7DeckingMode",
    "SkidderProductivityResult",
    "SkidderSpeedProfile",
    "ADV6N7Metadata",
    "ADV6N7SkidderResult",
    "estimate_grapple_skidder_productivity_han2018",
    "estimate_grapple_skidder_productivity_adv6n7",
    "get_skidder_speed_profile",
    "get_adv6n7_metadata",
    "estimate_cable_skidder_productivity_adv1n12_full_tree",
    "estimate_cable_skidder_productivity_adv1n12_two_phase",
]
_SKIDDER_SPEED_PROFILE_PATH = Path(__file__).resolve().parents[3] / "data" / "reference" / "skidder_speed_zurita2025.json"
