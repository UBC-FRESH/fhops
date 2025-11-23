"""Cable logging productivity helpers (Ünver-Okan 2020; Lee et al. 2018; TR125/TR127)."""

from __future__ import annotations

import contextlib
import json
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from fhops.reference import get_appendix5_profile, load_fncy12_dataset


_FEET_PER_METER = 3.28084
_CUBIC_FEET_PER_CUBIC_METER = 35.3146667
_LB_TO_KG = 0.45359237
_KG_TO_LB = 1.0 / _LB_TO_KG


_RUNNING_SKYLINE_VARIANTS = {
    "yarder_a": {"pieces_per_cycle": 2.8, "piece_volume_m3": 2.5, "z1": 0.0},
    "yarder_b": {"pieces_per_cycle": 3.0, "piece_volume_m3": 1.6, "z1": 1.0},
}

_TR125_SINGLE_SLOPE_RANGE = (10.0, 350.0)
_TR125_MULTI_SLOPE_RANGE = (10.0, 420.0)
_TR125_LATERAL_RANGE = (0.0, 50.0)


class Fncy12ProductivityVariant(str, Enum):
    """Variants of the FNCY12 Thunderbird TMY45 productivity study."""

    OVERALL = "overall"
    STEADY_STATE = "steady_state"
    STEADY_STATE_NO_FIRE = "steady_state_no_fire"


@dataclass(frozen=True)
class Fncy12ProductivityResult:
    """Summary of the FNCY12 productivity calculations."""

    variant: Fncy12ProductivityVariant
    shift_productivity_m3: float
    shift_hours: float
    productivity_m3_per_pmh: float


def _validate_inputs(log_volume_m3: float, route_slope_percent: float) -> None:
    """Ensure log volume and slope inputs are positive before running regressions."""
    if log_volume_m3 <= 0:
        raise ValueError("log_volume_m3 must be > 0")
    if route_slope_percent <= 0:
        raise ValueError("route_slope_percent must be > 0")


def estimate_cable_skidding_productivity_unver_spss(
    log_volume_m3: float, route_slope_percent: float
) -> float:
    """Estimate skyline-skidding productivity (m³/h) via Ünver & Okan (2020) SPSS regression.

    Parameters
    ----------
    log_volume_m3 : float
        Average log volume per turn (m³). Calibrated range ≈0.2–1.0 m³.
    route_slope_percent : float
        Uphill skyline slope (%). Positive values only; typical study range was 5–60 %.

    Returns
    -------
    float
        Predicted productivity in cubic metres per scheduled hour (delay-free). Values are clipped at
        zero to avoid negative outputs when very steep slopes are supplied.
    """

    _validate_inputs(log_volume_m3, route_slope_percent)
    value = 4.188 + 5.325 * log_volume_m3 - 2.392 * route_slope_percent / 100.0
    return max(value, 0.0)


def estimate_cable_skidding_productivity_unver_robust(
    log_volume_m3: float, route_slope_percent: float
) -> float:
    """Estimate skyline-skidding productivity (m³/h) using the robust Ünver & Okan fit.

    Parameters
    ----------
    log_volume_m3 : float
        Average log volume per turn (m³).
    route_slope_percent : float
        Skyline slope (%). Positive values only.

    Returns
    -------
    float
        Delay-free productivity in m³/h (clipped at zero for extreme slopes).
    """

    _validate_inputs(log_volume_m3, route_slope_percent)
    value = 3.0940 + 5.5182 * log_volume_m3 - 1.3886 * route_slope_percent / 100.0
    return max(value, 0.0)


def _profile_slope_percent(profile: str) -> float:
    """Return slope (%) derived from an Appendix 5 profile record."""
    record = get_appendix5_profile(profile)
    slope = record.average_slope_percent
    if slope is None:
        raise ValueError(f"Profile '{profile}' does not include a usable slope.")
    return slope


def estimate_cable_skidding_productivity_unver_spss_profile(
    *,
    profile: str,
    log_volume_m3: float,
) -> float:
    """Profile-aware SPSS regression that derives slope (%) from Appendix 5 data.

    Parameters
    ----------
    profile : str
        Stand profile identifier recognised by :func:`fhops.reference.get_appendix5_profile`.
    log_volume_m3 : float
        Average log volume per turn (m³).

    Returns
    -------
    float
        Delay-free productivity in m³/h.
    """

    slope = _profile_slope_percent(profile)
    return estimate_cable_skidding_productivity_unver_spss(log_volume_m3, slope)


def estimate_cable_skidding_productivity_unver_robust_profile(
    *,
    profile: str,
    log_volume_m3: float,
) -> float:
    """Profile-aware robust regression for skyline skidding (Ünver & Okan 2020).

    Parameters
    ----------
    profile : str
        Appendix 5 stand identifier providing the route slope (%).
    log_volume_m3 : float
        Average log volume per turn (m³).

    Returns
    -------
    float
        Delay-free productivity in m³/h using the robust fit.
    """

    slope = _profile_slope_percent(profile)
    return estimate_cable_skidding_productivity_unver_robust(log_volume_m3, slope)


def _validate_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _validate_non_negative(value: float, name: str) -> None:
    """Validate that ``value`` is non-negative."""
    if value < 0:
        raise ValueError(f"{name} must be >= 0")


def _m3_per_pmh(payload_m3: float, cycle_seconds: float) -> float:
    """Convert payload (m³) and cycle seconds to m³ per productive machine hour."""
    _validate_positive(payload_m3, "payload_m3")
    _validate_positive(cycle_seconds, "cycle_seconds")
    return payload_m3 * (3600.0 / cycle_seconds)


def _m3_per_pmh_from_minutes(payload_m3: float, cycle_minutes: float) -> float:
    """Convert payload (m³) and cycle minutes to m³ per productive machine hour."""
    _validate_positive(payload_m3, "payload_m3")
    _validate_positive(cycle_minutes, "cycle_minutes")
    return payload_m3 * (60.0 / cycle_minutes)


def estimate_cable_yarder_productivity_lee2018_uphill(
    *,
    yarding_distance_m: float,
    payload_m3: float = 0.57,
) -> float:
    """
    Estimate uphill yarder productivity (m³/PMH) using Lee et al. (2018) Eq. 1.

    Parameters
    ----------
    yarding_distance_m:
        Skyline distance from stump to landing (metres). Regression calibrated
        for 5–130 m (mean 55 m) in 40% slopes.
    payload_m3:
        Volume yarded per cycle (default 0.57 m³, Lee et al. Table 3).
    """

    _validate_positive(yarding_distance_m, "yarding_distance_m")
    cycle_seconds = 135.421 + 1.908 * yarding_distance_m
    return _m3_per_pmh(payload_m3, cycle_seconds)


def estimate_cable_yarder_productivity_lee2018_downhill(
    *,
    yarding_distance_m: float,
    lateral_distance_m: float,
    large_end_diameter_cm: float,
    payload_m3: float = 0.61,
) -> float:
    """
    Estimate downhill yarder productivity (m³/PMH) using Lee et al. (2018) Eq. 2.

    Parameters
    ----------
    yarding_distance_m:
        Skyline distance from stump to landing (metres). Calibrated for 10–90 m (mean 53 m).
    lateral_distance_m:
        Average lateral yarding distance (metres). Calibrated for 0–25 m (mean 5 m).
    large_end_diameter_cm:
        Diameter at the large end of the log (centimetres), ~34 cm in the case study.
    payload_m3:
        Volume yarded per cycle (default 0.61 m³, Lee et al. Table 3).
    """

    _validate_positive(yarding_distance_m, "yarding_distance_m")
    _validate_positive(lateral_distance_m, "lateral_distance_m")
    _validate_positive(large_end_diameter_cm, "large_end_diameter_cm")
    cycle_seconds = (
        128.158
        + 1.408 * large_end_diameter_cm
        + 1.610 * yarding_distance_m
        + 3.057 * lateral_distance_m
    )
    return _m3_per_pmh(payload_m3, cycle_seconds)


def estimate_cable_yarder_cycle_time_tr125_single_span(
    *, slope_distance_m: float, lateral_distance_m: float
) -> float:
    """Delay-free cycle time (minutes) for TR-125 single-span skyline yarding.

    Parameters
    ----------
    slope_distance_m : float
        Skyline slope distance (metres). Valid for 10–350 m.
    lateral_distance_m : float
        Lateral reach (metres). Valid for 0–50 m.
    """
    _validate_positive(slope_distance_m, "slope_distance_m")
    _validate_positive(lateral_distance_m, "lateral_distance_m")
    _warn_if_out_of_range("slope_distance_m", slope_distance_m, _TR125_SINGLE_SLOPE_RANGE)
    _warn_if_out_of_range("lateral_distance_m", lateral_distance_m, _TR125_LATERAL_RANGE)
    return 2.76140 + 0.00449 * slope_distance_m + 0.03750 * lateral_distance_m


def estimate_cable_yarder_productivity_tr125_single_span(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    payload_m3: float = 1.6,
) -> float:
    """Productivity (m³/PMH) for single-span skyline yarding (TR-125 Eq. 1).

    Parameters
    ----------
    slope_distance_m : float
        Skyline slope distance (metres). Regression calibrated for 10–350 m.
    lateral_distance_m : float
        Lateral skyline distance (metres). Regression calibrated for 0–50 m.
    payload_m3 : float, default=1.6
        Payload per cycle (m³). Defaults to the TR-125 observation mean (~1.6 m³).
    """

    _validate_positive(slope_distance_m, "slope_distance_m")
    _validate_positive(lateral_distance_m, "lateral_distance_m")
    cycle_minutes = estimate_cable_yarder_cycle_time_tr125_single_span(
        slope_distance_m=slope_distance_m,
        lateral_distance_m=lateral_distance_m,
    )
    return _m3_per_pmh_from_minutes(payload_m3, cycle_minutes)


def estimate_cable_yarder_cycle_time_tr125_multi_span(
    *, slope_distance_m: float, lateral_distance_m: float
) -> float:
    """Delay-free cycle time (minutes) for TR-125 multi-span skyline yarding.

    Parameters
    ----------
    slope_distance_m : float
        Skyline slope distance (metres). Valid for 10–420 m.
    lateral_distance_m : float
        Lateral reach (metres). Valid for 0–50 m.
    """
    _validate_positive(slope_distance_m, "slope_distance_m")
    _validate_positive(lateral_distance_m, "lateral_distance_m")
    _warn_if_out_of_range("slope_distance_m", slope_distance_m, _TR125_MULTI_SLOPE_RANGE)
    _warn_if_out_of_range("lateral_distance_m", lateral_distance_m, _TR125_LATERAL_RANGE)
    return 2.43108 + 0.00910 * slope_distance_m + 0.02563 * lateral_distance_m


def estimate_cable_yarder_productivity_tr125_multi_span(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    payload_m3: float = 1.6,
) -> float:
    """Productivity (m³/PMH) for multi-span skyline yarding (TR-125 Eq. 2).

    Parameters
    ----------
    slope_distance_m : float
        Skyline slope distance (metres). Regression calibrated for 10–420 m.
    lateral_distance_m : float
        Lateral skyline distance (metres). Regression calibrated for 0–50 m.
    payload_m3 : float, default=1.6
        Payload per cycle (m³). Defaults to the TR-125 observation mean (~1.6 m³).
    """

    _validate_positive(slope_distance_m, "slope_distance_m")
    _validate_positive(lateral_distance_m, "lateral_distance_m")
    cycle_minutes = estimate_cable_yarder_cycle_time_tr125_multi_span(
        slope_distance_m=slope_distance_m,
        lateral_distance_m=lateral_distance_m,
    )
    return _m3_per_pmh_from_minutes(payload_m3, cycle_minutes)


def _running_skyline_variant(key: str) -> dict[str, float]:
    """Return running-skyline preset parameters (pieces/turn, volume, z1) by key."""
    normalized = key.lower()
    if normalized not in _RUNNING_SKYLINE_VARIANTS:
        allowed = ", ".join(sorted(_RUNNING_SKYLINE_VARIANTS))
        raise ValueError(f"Unknown running-skyline variant '{key}'. Expected one of: {allowed}.")
    return _RUNNING_SKYLINE_VARIANTS[normalized]


def estimate_running_skyline_cycle_time_mcneel2000_minutes(
    *,
    horizontal_distance_m: float,
    lateral_distance_m: float,
    vertical_distance_m: float,
    pieces_per_cycle: float | None = None,
    yarder_variant: str = "yarder_a",
) -> float:
    """Scheduled cycle time (minutes) for running skyline yarders (McNeel 2000).

    Parameters
    ----------
    horizontal_distance_m : float
        Horizontal skyline distance (metres).
    lateral_distance_m : float
        Average lateral yarding distance (metres). Non-negative.
    vertical_distance_m : float
        Vertical difference between landing and payload (metres). Non-negative.
    pieces_per_cycle : float, optional
        Pieces (logs) handled per cycle. Defaults to the selected variant mean.
    yarder_variant : str, default="yarder_a"
        Named variant from McNeel (2000) Table 4 (``yarder_a`` or ``yarder_b``).

    Returns
    -------
    float
        Scheduled cycle time in minutes.

    References
    ----------
    McNeel, J.F. (2000). *Modeling Production of Longline Yarding Operations in Coastal British
    Columbia*. Journal of Forest Engineering 11(1):29–38.
    """

    _validate_positive(horizontal_distance_m, "horizontal_distance_m")
    _validate_non_negative(lateral_distance_m, "lateral_distance_m")
    _validate_non_negative(vertical_distance_m, "vertical_distance_m")
    variant = _running_skyline_variant(yarder_variant)
    pieces = pieces_per_cycle if pieces_per_cycle is not None else variant["pieces_per_cycle"]
    _validate_positive(pieces, "pieces_per_cycle")
    z1 = variant["z1"]
    cycle_minutes = (
        10.167
        + 0.00490 * horizontal_distance_m
        + 0.01836 * vertical_distance_m
        - 0.011080 * z1 * vertical_distance_m
        + 0.080542 * lateral_distance_m
        + 0.109484 * pieces
        - 1.18 * z1
    )
    return max(cycle_minutes, 0.0)


def estimate_running_skyline_productivity_mcneel2000(
    *,
    horizontal_distance_m: float,
    lateral_distance_m: float,
    vertical_distance_m: float,
    pieces_per_cycle: float | None = None,
    piece_volume_m3: float | None = None,
    yarder_variant: str = "yarder_a",
) -> float:
    """Running skyline productivity (m³/PMH0) using McNeel (2000) regressions.

    Parameters
    ----------
    horizontal_distance_m, lateral_distance_m, vertical_distance_m : float
        Predictor distances (metres) matching the cycle-time helper.
    pieces_per_cycle : float, optional
        Pieces (logs) hauled per cycle. Defaults to the selected variant's mean.
    piece_volume_m3 : float, optional
        Volume per piece (m³). Defaults to variant-specific values.
    yarder_variant : str, default="yarder_a"
        ``yarder_a`` or ``yarder_b`` from McNeel (2000) Table 4.

    Returns
    -------
    float
        Delay-free productivity in m³/PMH0.
    """

    variant = _running_skyline_variant(yarder_variant)
    pieces = pieces_per_cycle if pieces_per_cycle is not None else variant["pieces_per_cycle"]
    volume = piece_volume_m3 if piece_volume_m3 is not None else variant["piece_volume_m3"]
    _validate_positive(volume, "piece_volume_m3")
    payload_m3 = pieces * volume
    cycle_minutes = estimate_running_skyline_cycle_time_mcneel2000_minutes(
        horizontal_distance_m=horizontal_distance_m,
        lateral_distance_m=lateral_distance_m,
        vertical_distance_m=vertical_distance_m,
        pieces_per_cycle=pieces,
        yarder_variant=yarder_variant,
    )
    return _m3_per_pmh_from_minutes(payload_m3, cycle_minutes)


class HelicopterLonglineModel(str, Enum):
    """Supported helicopter models used in FPInnovations longline studies."""

    LAMA = "lama"
    KMAX = "kmax"
    BELL_214B = "bell214b"
    S64E_AIRCRANE = "s64e_aircrane"
    KA32A = "ka32a"


@dataclass(frozen=True)
class HelicopterSpec:
    """Performance metadata for a helicopter longline configuration."""

    model: HelicopterLonglineModel
    rated_payload_kg: float
    default_load_factor: float
    weight_to_volume_kg_per_m3: float
    hook_breakout_minutes: float
    unhook_minutes: float
    fly_empty_speed_mps: float
    fly_loaded_speed_mps: float

    @property
    def default_payload_kg(self) -> float:
        """Return the default payload (kg) after applying the study's load factor."""
        return self.rated_payload_kg * self.default_load_factor

    @property
    def rated_payload_lb(self) -> float:
        """Return the rated payload expressed in pounds."""
        return self.rated_payload_kg * _KG_TO_LB


_HELICOPTER_SPECS: dict[HelicopterLonglineModel, HelicopterSpec] = {
    HelicopterLonglineModel.LAMA: HelicopterSpec(
        model=HelicopterLonglineModel.LAMA,
        rated_payload_kg=2_500.0 * _LB_TO_KG,
        default_load_factor=0.8,
        weight_to_volume_kg_per_m3=2_972.0 * _LB_TO_KG,
        hook_breakout_minutes=0.8,
        unhook_minutes=0.15,
        fly_empty_speed_mps=22.0,
        fly_loaded_speed_mps=18.0,
    ),
    HelicopterLonglineModel.KMAX: HelicopterSpec(
        model=HelicopterLonglineModel.KMAX,
        rated_payload_kg=6_000.0 * _LB_TO_KG,
        default_load_factor=0.75,
        weight_to_volume_kg_per_m3=2_972.0 * _LB_TO_KG,
        hook_breakout_minutes=0.77,
        unhook_minutes=0.14,
        fly_empty_speed_mps=18.3,
        fly_loaded_speed_mps=13.6,
    ),
    HelicopterLonglineModel.BELL_214B: HelicopterSpec(
        model=HelicopterLonglineModel.BELL_214B,
        rated_payload_kg=8_000.0 * _LB_TO_KG,
        default_load_factor=0.7,
        weight_to_volume_kg_per_m3=2_375.0 * _LB_TO_KG,
        hook_breakout_minutes=1.1,
        unhook_minutes=0.28,
        fly_empty_speed_mps=23.5,
        fly_loaded_speed_mps=19.3,
    ),
    HelicopterLonglineModel.KA32A: HelicopterSpec(
        model=HelicopterLonglineModel.KA32A,
        rated_payload_kg=5_000.0,
        default_load_factor=0.6,
        weight_to_volume_kg_per_m3=2_787.0 * _LB_TO_KG,
        hook_breakout_minutes=0.9,
        unhook_minutes=0.46,
        fly_empty_speed_mps=7.8,
        fly_loaded_speed_mps=6.7,
    ),
    HelicopterLonglineModel.S64E_AIRCRANE: HelicopterSpec(
        model=HelicopterLonglineModel.S64E_AIRCRANE,
        rated_payload_kg=20_000.0 * _LB_TO_KG,
        default_load_factor=0.7,
        weight_to_volume_kg_per_m3=2_700.0 * _LB_TO_KG,
        hook_breakout_minutes=1.9,
        unhook_minutes=0.22,
        fly_empty_speed_mps=33.0,
        fly_loaded_speed_mps=27.0,
    ),
}


@dataclass(frozen=True)
class HelicopterProductivityResult:
    """Structured output for helicopter longline productivity estimates."""

    model: HelicopterLonglineModel
    flight_distance_m: float
    payload_m3: float
    payload_kg: float
    payload_lb: float
    load_factor: float
    cycle_minutes: float
    turns_per_pmh0: float
    productivity_m3_per_pmh0: float
    additional_delay_minutes: float
    spec: HelicopterSpec
    weight_to_volume_kg_per_m3: float
    weight_to_volume_lb_per_m3: float


def _helicopter_spec(model: HelicopterLonglineModel) -> HelicopterSpec:
    """Return the helicopter specification for a supported model."""
    try:
        return _HELICOPTER_SPECS[model]
    except KeyError as exc:
        raise ValueError(f"Unsupported helicopter model: {model}") from exc


def estimate_helicopter_longline_productivity(
    *,
    model: HelicopterLonglineModel,
    flight_distance_m: float,
    payload_m3: float | None = None,
    load_factor: float | None = None,
    weight_to_volume_lb_per_m3: float | None = None,
    additional_delay_minutes: float = 0.0,
) -> HelicopterProductivityResult:
    """Estimate helicopter longline productivity (m³/PMH0) using FPInnovations case studies.

    Parameters
    ----------
    model : HelicopterLonglineModel
        Aircraft preset (Lama, K-Max, Bell 214B, KA-32A, or S-64E Aircrane).
    flight_distance_m : float
        One-way flight distance between landing and drop site (metres). Must be > 0.
    payload_m3 : float, optional
        Explicit payload volume per turn (m³). When omitted, a payload is derived from the rated
        payload and ``load_factor``.
    load_factor : float, optional
        Fraction of rated payload utilised (0 < factor ≤ 1). Defaults to the published value for the
        chosen model.
    weight_to_volume_lb_per_m3 : float, optional
        Conversion from payload weight (lb) to volume (m³). Defaults to species-specific values
        published in the FPInnovations studies; supply this when operating outside the default wood
        density.
    additional_delay_minutes : float, default=0.0
        Extra minutes per cycle (landing congestion, hover delays, etc.) added on top of the published
        hook/unhook times.

    Returns
    -------
    HelicopterProductivityResult
        Dataclass containing payload in m³/kg/lb, turns per hour, PMH0 productivity, and the aircraft
        spec used for the calculation.

    Notes
    -----
    The helper assumes symmetric empty/loaded flight paths of length ``flight_distance_m``. Use the
    CLI wrappers if you need to feed telemetry or capture JSON outputs from case-study presets.
    """

    if flight_distance_m <= 0:
        raise ValueError("flight_distance_m must be > 0")
    if additional_delay_minutes < 0:
        raise ValueError("additional_delay_minutes must be >= 0")

    spec = _helicopter_spec(model)
    if weight_to_volume_lb_per_m3 is not None:
        conversion_kg = weight_to_volume_lb_per_m3 * _LB_TO_KG
        conversion_lb = float(weight_to_volume_lb_per_m3)
    else:
        conversion_kg = spec.weight_to_volume_kg_per_m3
        conversion_lb = spec.weight_to_volume_kg_per_m3 * _KG_TO_LB

    if payload_m3 is not None and payload_m3 <= 0:
        raise ValueError("payload_m3 must be > 0 when specified.")
    if load_factor is not None and not (0.0 < load_factor <= 1.0):
        raise ValueError("load_factor must lie in (0, 1].")

    if payload_m3 is not None:
        payload_kg = payload_m3 * conversion_kg
        load_factor_value = payload_kg / spec.rated_payload_kg
    else:
        load_factor_value = load_factor if load_factor is not None else spec.default_load_factor
        payload_kg = spec.rated_payload_kg * load_factor_value
        payload_m3 = payload_kg / conversion_kg

    if load_factor_value <= 0 or payload_kg <= 0:
        raise ValueError("Computed payload is not positive; check inputs.")
    payload_lb = payload_kg * _KG_TO_LB

    fly_empty_minutes = (flight_distance_m / spec.fly_empty_speed_mps) / 60.0
    fly_loaded_minutes = (flight_distance_m / spec.fly_loaded_speed_mps) / 60.0
    cycle_minutes = (
        spec.hook_breakout_minutes
        + spec.unhook_minutes
        + fly_empty_minutes
        + fly_loaded_minutes
        + additional_delay_minutes
    )
    turns_per_hour = 60.0 / cycle_minutes
    productivity = payload_m3 * turns_per_hour

    return HelicopterProductivityResult(
        model=model,
        flight_distance_m=flight_distance_m,
        payload_m3=payload_m3,
        payload_kg=payload_kg,
        payload_lb=payload_lb,
        load_factor=load_factor_value,
        cycle_minutes=cycle_minutes,
        turns_per_pmh0=turns_per_hour,
        productivity_m3_per_pmh0=productivity,
        additional_delay_minutes=additional_delay_minutes,
        spec=spec,
        weight_to_volume_kg_per_m3=conversion_kg,
        weight_to_volume_lb_per_m3=conversion_lb,
    )


def estimate_standing_skyline_turn_time_aubuchon1979(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    logs_per_turn: float,
    crew_size: float,
) -> float:
    """Delay-free turn time (minutes) from Hensel et al. (1979) / Aubuchon (1982).

    Parameters
    ----------
    slope_distance_m : float
        Skyline slope distance (metres). Published range ≈300–900 m (converted from feet).
    lateral_distance_m : float
        Lateral reach (metres). Published range 15–45 m.
    logs_per_turn : float
        Number of logs per cycle (3.5–6 in the study).
    crew_size : float
        Crew size (persons) influencing setup time.

    Notes
    -----
    The regression was published in imperial units; the helper converts to feet internally before
    applying the coefficients.
    """

    if logs_per_turn <= 0:
        raise ValueError("logs_per_turn must be > 0")
    if crew_size <= 0:
        raise ValueError("crew_size must be > 0")
    if slope_distance_m <= 0 or lateral_distance_m < 0:
        raise ValueError("Distances must be >= 0 and slope distance must be > 0")
    slope_distance_ft = slope_distance_m * _FEET_PER_METER
    lateral_distance_ft = lateral_distance_m * _FEET_PER_METER
    # Hensel et al. (1979) regression (minutes), Appendix A eq. 15 in Aubuchon (1982)
    return (
        5.102
        + 0.970 * logs_per_turn
        + 0.00000172 * (slope_distance_ft ** 2)
        + 0.031 * lateral_distance_ft
        - 0.194 * crew_size
    )


def estimate_standing_skyline_productivity_aubuchon1979(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    logs_per_turn: float,
    average_log_volume_m3: float,
    crew_size: float,
) -> float:
    """Standing skyline productivity (m³/PMH0) via Aubuchon (1982).

    Parameters
    ----------
    slope_distance_m, lateral_distance_m : float
        Distances in metres passed to :func:`estimate_standing_skyline_turn_time_aubuchon1979`.
    logs_per_turn : float
        Logs per cycle.
    average_log_volume_m3 : float
        Mean volume per log (m³).
    crew_size : float
        Crew size (persons).

    Returns
    -------
    float
        Delay-free productivity in m³/PMH0.
    """

    if average_log_volume_m3 <= 0:
        raise ValueError("average_log_volume_m3 must be > 0")
    turn_minutes = estimate_standing_skyline_turn_time_aubuchon1979(
        slope_distance_m=slope_distance_m,
        lateral_distance_m=lateral_distance_m,
        logs_per_turn=logs_per_turn,
        crew_size=crew_size,
    )
    payload_m3 = average_log_volume_m3 * logs_per_turn
    return _m3_per_pmh_from_minutes(payload_m3, turn_minutes)


def estimate_standing_skyline_turn_time_kramer1978(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    logs_per_turn: float,
    carriage_height_m: float,
    chordslope_percent: float,
) -> float:
    """Delay-free turn time (min) from Kramer (1978) standing-skyline trials (Aubuchon Appendix A)."""

    if logs_per_turn <= 0:
        raise ValueError("logs_per_turn must be > 0")
    if slope_distance_m <= 0 or lateral_distance_m < 0:
        raise ValueError("Distances must be >= 0 and slope distance must be > 0")
    if carriage_height_m < 0:
        raise ValueError("carriage_height_m must be >= 0")
    slope_distance_ft = slope_distance_m * _FEET_PER_METER
    lateral_distance_ft = lateral_distance_m * _FEET_PER_METER
    carriage_height_ft = carriage_height_m * _FEET_PER_METER
    minutes = (
        0.68620
        + 0.00525 * slope_distance_ft
        + 0.01243 * lateral_distance_ft
        + 0.27960 * logs_per_turn
        + 0.01759 * carriage_height_ft
        + 0.02521 * chordslope_percent
    )
    return max(minutes, 0.01)


def estimate_standing_skyline_productivity_kramer1978(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    logs_per_turn: float,
    average_log_volume_m3: float,
    carriage_height_m: float,
    chordslope_percent: float,
) -> float:
    """Estimate standing skyline productivity (m³/PMH0) via Kramer (1978) regression."""

    if average_log_volume_m3 <= 0:
        raise ValueError("average_log_volume_m3 must be > 0")
    turn_minutes = estimate_standing_skyline_turn_time_kramer1978(
        slope_distance_m=slope_distance_m,
        lateral_distance_m=lateral_distance_m,
        logs_per_turn=logs_per_turn,
        carriage_height_m=carriage_height_m,
        chordslope_percent=chordslope_percent,
    )
    payload_m3 = average_log_volume_m3 * logs_per_turn
    return _m3_per_pmh_from_minutes(payload_m3, turn_minutes)


def estimate_standing_skyline_turn_time_kellogg1976(
    *,
    slope_distance_m: float,
    lead_angle_degrees: float,
    logs_per_turn: float,
    average_log_volume_m3: float,
    chokers: float,
) -> float:
    """Delay-free turn time (min) from Kellogg (1976) standing yarder study (Aubuchon Appendix A)."""

    if logs_per_turn <= 0:
        raise ValueError("logs_per_turn must be > 0")
    if average_log_volume_m3 <= 0:
        raise ValueError("average_log_volume_m3 must be > 0")
    if chokers <= 0:
        raise ValueError("chokers must be > 0")
    if slope_distance_m <= 0:
        raise ValueError("slope_distance_m must be > 0")
    slope_distance_ft = slope_distance_m * _FEET_PER_METER
    payload_m3 = average_log_volume_m3 * logs_per_turn
    payload_ft3 = payload_m3 * _CUBIC_FEET_PER_CUBIC_METER
    minutes = (
        -2.8897
        + 0.028864 * slope_distance_ft
        + 0.010653 * lead_angle_degrees
        + 0.036543 * payload_ft3
        + 2.1101 * chokers
    )
    return max(minutes, 0.01)


def estimate_standing_skyline_productivity_kellogg1976(
    *,
    slope_distance_m: float,
    lead_angle_degrees: float,
    logs_per_turn: float,
    average_log_volume_m3: float,
    chokers: float,
) -> float:
    """Standing skyline productivity (m³/PMH0) via Kellogg (1976) regression.

    Parameters
    ----------
    slope_distance_m : float
        Skyline slope distance (metres).
    lead_angle_degrees : float
        Lead angle (degrees).
    logs_per_turn : float
        Logs per cycle.
    average_log_volume_m3 : float
        Average log volume (m³).
    chokers : float
        Number of chokers used in the crew.
    """

    turn_minutes = estimate_standing_skyline_turn_time_kellogg1976(
        slope_distance_m=slope_distance_m,
        lead_angle_degrees=lead_angle_degrees,
        logs_per_turn=logs_per_turn,
        average_log_volume_m3=average_log_volume_m3,
        chokers=chokers,
    )
    payload_m3 = average_log_volume_m3 * logs_per_turn
    return _m3_per_pmh_from_minutes(payload_m3, turn_minutes)


def running_skyline_variant_defaults(yarder_variant: str) -> tuple[float, float]:
    """Return the `(pieces_per_cycle, piece_volume_m3)` defaults for a McNeel variant."""

    variant = _running_skyline_variant(yarder_variant)
    return variant["pieces_per_cycle"], variant["piece_volume_m3"]


def estimate_tmy45_productivity_fncy12(
    variant: Fncy12ProductivityVariant = Fncy12ProductivityVariant.STEADY_STATE,
) -> Fncy12ProductivityResult:
    """Return TMY45 + Mini-Mak II productivity metrics from the FNCY12 dataset.

    Parameters
    ----------
    variant : Fncy12ProductivityVariant, default=STEADY_STATE
        Choice between overall average, steady-state average (last 3 months), or steady-state with fire
        delays removed.

    Returns
    -------
    Fncy12ProductivityResult
        Dataclass containing shift-level productivity (m³), shift hours, and PMH0 output.
    """
    dataset = load_fncy12_dataset()
    totals = dataset.productivity_totals or {}
    variant_map = {
        Fncy12ProductivityVariant.OVERALL: totals.get("avg_shift_m3"),
        Fncy12ProductivityVariant.STEADY_STATE: totals.get("avg_shift_m3_last_three_months"),
        Fncy12ProductivityVariant.STEADY_STATE_NO_FIRE: totals.get(
            "avg_shift_m3_last_three_months_no_fire_delays"
        ),
    }
    shift_m3 = variant_map.get(variant)
    if not isinstance(shift_m3, (int, float)):
        raise ValueError(f"FNCY12 dataset missing shift output for variant '{variant.value}'.")
    shift_hours = dataset.shift_hours or 10.0
    productivity = float(shift_m3) / shift_hours
    return Fncy12ProductivityResult(
        variant=variant,
        shift_productivity_m3=float(shift_m3),
        shift_hours=shift_hours,
        productivity_m3_per_pmh=productivity,
    )


@dataclass(frozen=True)
class _TR127Predictor:
    """Predictor metadata for TR-127 regressions (name, units, range, coefficient)."""

    name: str
    units: str
    value_range: tuple[float, float]
    coefficient: float


@dataclass(frozen=True)
class _TR127Regression:
    """TR-127 regression definition (block, intercept, predictor list)."""

    block: int
    description: str
    intercept_minutes: float
    predictors: tuple[_TR127Predictor, ...]


_TR127_REGRESSIONS_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tr127_regressions.json"
)


@lru_cache(maxsize=1)
def _load_tr127_models() -> Mapping[int, _TR127Regression]:
    """Load TR-127 regression definitions (cached) from the bundled JSON dataset."""
    if not _TR127_REGRESSIONS_PATH.exists():
        raise FileNotFoundError(f"TR127 regression data not found: {_TR127_REGRESSIONS_PATH}")
    with _TR127_REGRESSIONS_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    models: dict[int, _TR127Regression] = {}
    for entry in payload:
        predictors = tuple(
            _TR127Predictor(
                name=predictor["name"],
                units=predictor.get("units", ""),
                value_range=tuple(predictor.get("range", (float("-inf"), float("inf")))),
                coefficient=predictor["coefficient"],
            )
            for predictor in entry.get("predictors", [])
        )
        models[entry["block"]] = _TR127Regression(
            block=entry["block"],
            description=entry.get("description", f"Block {entry['block']}"),
            intercept_minutes=entry["intercept_minutes"],
            predictors=predictors,
        )
    return models


def _ensure_tr127_inputs(
    block: int,
    slope_distance_m: float | None,
    lateral_distance_m: float | None,
    num_logs: float | None,
    lateral_distance2_m: float | None = None,
) -> dict[str, float]:
    """Validate and collect predictor inputs required for a TR-127 block regression."""
    model = _load_tr127_models().get(block)
    if model is None:
        raise ValueError(f"Unknown TR127 block: {block}")
    values: dict[str, float] = {}
    for predictor in model.predictors:
        if predictor.name == "sd":
            if slope_distance_m is None:
                raise ValueError(f"Block {block} requires slope distance (m).")
            values["sd"] = slope_distance_m
        elif predictor.name == "latd":
            if lateral_distance_m is None:
                raise ValueError(f"Block {block} requires lateral distance (m).")
            values["latd"] = lateral_distance_m
        elif predictor.name == "logs":
            if num_logs is None:
                raise ValueError(f"Block {block} requires number of logs per turn.")
            values["logs"] = num_logs
        elif predictor.name == "latd2":
            if lateral_distance2_m is None:
                raise ValueError(f"Block {block} requires lateral distance (m) (latd2).")
            values["latd2"] = lateral_distance2_m
        else:
            raise ValueError(f"Unsupported TR127 predictor '{predictor.name}'.")
    return values


def _warn_if_out_of_range(name: str, value: float, value_range: tuple[float, float]) -> None:
    """Emit a warning when a predictor value falls outside its calibrated range."""
    lower, upper = value_range
    if (value < lower) or (value > upper):
        warnings.warn(
            f"Value {value:.2f} for {name} lies outside the calibrated range [{lower}, {upper}].",
            RuntimeWarning,
            stacklevel=2,
        )


def estimate_cable_yarder_cycle_time_tr127_minutes(
    *,
    block: int,
    slope_distance_m: float | None = None,
    lateral_distance_m: float | None = None,
    num_logs: float | None = None,
    lateral_distance2_m: float | None = None,
) -> float:
    """Delay-free cycle time (minutes) using TR127 Appendix VII regressions.

    Parameters
    ----------
    block : int
        Block identifier (1–6) corresponding to the published regression.
    slope_distance_m, lateral_distance_m, num_logs, lateral_distance2_m : float, optional
        Predictor values required by the chosen block model. Values outside the calibrated
        range emit warnings but are still evaluated.
    """

    model = _load_tr127_models().get(block)
    if model is None:
        raise ValueError(f"Unknown TR127 block: {block}")
    values = _ensure_tr127_inputs(
        block, slope_distance_m, lateral_distance_m, num_logs, lateral_distance2_m
    )
    cycle_minutes = model.intercept_minutes
    for predictor in model.predictors:
        value = values[predictor.name]
        _warn_if_out_of_range(predictor.name, value, predictor.value_range)
        cycle_minutes += predictor.coefficient * value
    return cycle_minutes


def estimate_cable_yarder_productivity_tr127(
    *,
    block: int,
    payload_m3: float = 1.6,
    slope_distance_m: float | None = None,
    lateral_distance_m: float | None = None,
    num_logs: float | None = None,
    lateral_distance2_m: float | None = None,
) -> float:
    """TR127 skyline productivity (m³/PMH) using block-specific regressions.

    Parameters
    ----------
    block : int
        Block identifier (1–6).
    payload_m3 : float, default=1.6
        Payload per turn (m³). Defaults to TR127's reported mean.
    slope_distance_m, lateral_distance_m, num_logs, lateral_distance2_m : float, optional
        Predictors forwarded to :func:`estimate_cable_yarder_cycle_time_tr127_minutes`.
    """

    cycle_minutes = estimate_cable_yarder_cycle_time_tr127_minutes(
        block=block,
        slope_distance_m=slope_distance_m,
        lateral_distance_m=lateral_distance_m,
        num_logs=num_logs,
        lateral_distance2_m=lateral_distance2_m,
    )
    return _m3_per_pmh_from_minutes(payload_m3, cycle_minutes)


LEDOUX_COEFFICIENTS: dict[str, dict[str, float]] = {
    "skagit_shotgun": {
        "intercept": 2.74983,
        "x1": 0.00177,
        "x2": 0.12664,
        "x3": 0.00317,
        "x4": 0.20023,
        "x5": 0.00930,
    },
    "skagit_highlead": {
        "intercept": 3.08365,
        "x1": 0.00197,
        "x2": 0.16855,
        "x3": 0.00300,
        "x4": 0.12621,
        "x5": 0.00530,
    },
    "washington_208e": {
        "intercept": 3.77856,
        "x1": 0.00290,
        "x2": -0.11982,
        "x3": 0.00265,
        "x4": 0.48923,
        "x5": -0.00272,
    },
    "tmy45": {
        "intercept": 1.92641,
        "x1": 0.00423,
        "x2": 0.18713,
        "x3": 0.00674,
        "x4": 0.22898,
        "x5": 0.00482,
    },
}

FT_PER_M = 3.28084
CUBIC_FT_PER_CUBIC_M = 35.3147

MICRO_MASTER_DEFAULTS = {
    "constant_minutes": 5.108,  # Hookup + decking + unhook + road-change + minor delays (TN-54)
    "outhaul_speed_m_per_s": 4.1,
    "inhaul_speed_m_per_s": 2.1,
    "pieces_per_turn": 3.2,
    "piece_volume_m3": 0.46,
}

HI_SKID_DEFAULTS = {
    "constant_minutes": 2.6,  # Hookup + alignment + minor delays (derived from 4.16 m³/h @ 30 m, 0.24 m³ payload)
    "line_speed_m_per_min": 69.0,
    "pieces_per_cycle": 1.0,
    "piece_volume_m3": 0.24,
    "payload_per_load_m3": 12.0,
    "travel_to_dump_minutes": 30.0,
    "max_distance_m": 100.0,
}

@dataclass(frozen=True)
class TN173System:
    """
    FPInnovations TN-173 compact skyline system metadata.

    Attributes
    ----------
    system_id:
        Identifier from the bulletin.
    label:
        Display name for CLI/docs.
    operating_range_m:
        Recommended operating range (m).
    crew_size:
        Crew size used in the study.
    pieces_per_turn, piece_volume_m3, payload_m3:
        Payload descriptors per turn.
    cycle_minutes:
        Average cycle time (minutes).
    productivity_m3_per_pmh:
        Reported productivity (m³/PMH₀).
    average_yarding_distance_m, yarding_distance_min_m, yarding_distance_max_m:
        Yarding distance statistics (m).
    average_slope_percent, slope_percent_min, slope_percent_max:
        Slope statistics (%).
    notes:
        Additional notes for the system.
    """

    system_id: str
    label: str
    operating_range_m: float | None
    crew_size: float | None
    pieces_per_turn: float | None
    piece_volume_m3: float | None
    payload_m3: float | None
    cycle_minutes: float
    productivity_m3_per_pmh: float
    average_yarding_distance_m: float | None
    yarding_distance_min_m: float | None
    yarding_distance_max_m: float | None
    average_slope_percent: float | None
    slope_percent_min: float | None
    slope_percent_max: float | None
    notes: str | None


_TN173_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tn173_compact_yarders.json"
)


@lru_cache(maxsize=1)
def _load_tn173_systems() -> Mapping[str, TN173System]:
    """Load TN-173 skyline system metadata from the bundled JSON dataset."""
    if not _TN173_PATH.exists():
        raise FileNotFoundError(f"TN173 dataset not found: {_TN173_PATH}")
    with _TN173_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    systems: dict[str, TN173System] = {}
    for entry in payload.get("systems", []):
        system_id = str(entry["id"])
        study = entry.get("study", {})
        turn_profile = entry.get("turn_profile", {})
        layout = entry.get("layout", {})
        labour = entry.get("labour", {})

        avg_turn_volume = turn_profile.get("average_turn_volume_m3")
        avg_pieces = turn_profile.get("average_trees_per_turn")
        piece_volume = turn_profile.get("average_piece_volume_m3")
        if piece_volume is None and avg_turn_volume and avg_pieces:
            with contextlib.suppress(ZeroDivisionError):
                piece_volume = avg_turn_volume / avg_pieces

        yarding_range = layout.get("yarding_distance_range_m") or (None, None)
        slope_range = layout.get("slope_percent_range") or (None, None)

        systems[system_id] = TN173System(
            system_id=system_id,
            label=entry.get("name", entry.get("description", system_id)),
            operating_range_m=entry.get("operating_range_m"),
            crew_size=labour.get("crew_size_operational")
            or labour.get("crew_size_productive"),
            pieces_per_turn=float(avg_pieces) if avg_pieces is not None else None,
            piece_volume_m3=float(piece_volume) if piece_volume is not None else None,
            payload_m3=float(avg_turn_volume) if avg_turn_volume is not None else None,
            cycle_minutes=float(study.get("average_cycle_time_minutes", 0.0)),
            productivity_m3_per_pmh=float(study.get("productivity_m3_per_pmh", 0.0)),
            average_yarding_distance_m=float(layout.get("average_yarding_distance_m", 0.0))
            if layout.get("average_yarding_distance_m") is not None
            else None,
            yarding_distance_min_m=float(yarding_range[0]) if yarding_range[0] is not None else None,
            yarding_distance_max_m=float(yarding_range[1]) if len(yarding_range) > 1 and yarding_range[1] is not None else None,
            average_slope_percent=float(layout.get("average_slope_percent", 0.0))
            if layout.get("average_slope_percent") is not None
            else None,
            slope_percent_min=float(slope_range[0]) if slope_range[0] is not None else None,
            slope_percent_max=float(slope_range[1]) if len(slope_range) > 1 and slope_range[1] is not None else None,
            notes=entry.get("notes"),
        )
    return systems


def list_tn173_system_ids() -> tuple[str, ...]:
    """
    Return the available TN173 skyline system identifiers.

    Returns
    -------
    tuple[str, ...]
        Sorted tuple of system IDs.
    """
    systems = _load_tn173_systems()
    return tuple(sorted(systems))


def get_tn173_system(system_id: str) -> TN173System:
    """
    Return metadata for a given TN173 skyline system.

    Parameters
    ----------
    system_id:
        Identifier from :func:`list_tn173_system_ids`.

    Returns
    -------
    TN173System
        Dataclass containing payload, productivity, and range metadata.

    Raises
    ------
    KeyError
        If ``system_id`` is not present in the dataset.
    """
    systems = _load_tn173_systems()
    try:
        return systems[system_id]
    except KeyError as exc:
        raise KeyError(f"Unknown TN173 system '{system_id}'. Available: {', '.join(sorted(systems))}") from exc


def estimate_residue_cycle_time_ledoux_minutes(
    *,
    profile: str,
    slope_distance_m: float,
    merchantable_logs_per_turn: float,
    merchantable_volume_m3: float,
    residue_pieces_per_turn: float,
    residue_volume_m3: float,
) -> float:
    """Cycle time (minutes) for residue yarding using LeDoux (1981) regressions.

    Parameters
    ----------
    profile : str
        One of ``skagit_shotgun``, ``skagit_highlead``, ``washington_208e``, ``tmy45``.
    slope_distance_m : float
        Uphill skyline slope distance (metres).
    merchantable_logs_per_turn : float
        Count of merchantable logs per cycle.
    merchantable_volume_m3 : float
        Merchantable volume per cycle (m³).
    residue_pieces_per_turn : float
        Residue pieces per cycle.
    residue_volume_m3 : float
        Residue volume per cycle (m³).
    """
    coeffs = LEDOUX_COEFFICIENTS[profile]
    x1 = slope_distance_m * FT_PER_M
    x2 = merchantable_logs_per_turn
    x3 = merchantable_volume_m3 * CUBIC_FT_PER_CUBIC_M
    x4 = residue_pieces_per_turn
    x5 = residue_volume_m3 * CUBIC_FT_PER_CUBIC_M
    cycle = (
        coeffs["intercept"]
        + coeffs["x1"] * x1
        + coeffs["x2"] * x2
        + coeffs["x3"] * x3
        + coeffs["x4"] * x4
        + coeffs["x5"] * x5
    )
    return max(cycle, 0.01)


def estimate_residue_productivity_ledoux_m3_per_pmh(
    *,
    profile: str,
    slope_distance_m: float,
    merchantable_logs_per_turn: float,
    merchantable_volume_m3: float,
    residue_pieces_per_turn: float,
    residue_volume_m3: float,
) -> tuple[float, float]:
    """Residue and merchantable productivity (m³/PMH) using LeDoux regressions.

    Returns
    -------
    tuple
        ``(total_productivity_m3_per_pmh, cycle_minutes)``.
    """
    cycle_minutes = estimate_residue_cycle_time_ledoux_minutes(
        profile=profile,
        slope_distance_m=slope_distance_m,
        merchantable_logs_per_turn=merchantable_logs_per_turn,
        merchantable_volume_m3=merchantable_volume_m3,
        residue_pieces_per_turn=residue_pieces_per_turn,
        residue_volume_m3=residue_volume_m3,
    )
    total_volume_m3 = merchantable_volume_m3 + residue_volume_m3
    if total_volume_m3 <= 0:
        raise ValueError("Total volume per turn must be > 0 for LeDoux regressions")
    productivity = (total_volume_m3 * 60.0) / cycle_minutes
    return productivity, cycle_minutes


def ledoux_delay_component_minutes(
    *,
    profile: str,
    merchantable_logs_per_turn: float,
    merchantable_volume_m3: float,
    residue_pieces_per_turn: float,
    residue_volume_m3: float,
) -> tuple[float, float]:
    """Delay contributions (minutes) attributed to merchantable vs residue payload."""

    coeffs = LEDOUX_COEFFICIENTS[profile]
    x2 = merchantable_logs_per_turn
    x3 = merchantable_volume_m3 * CUBIC_FT_PER_CUBIC_M
    x4 = residue_pieces_per_turn
    x5 = residue_volume_m3 * CUBIC_FT_PER_CUBIC_M
    merch_minutes = coeffs["x2"] * x2 + coeffs["x3"] * x3
    residue_minutes = coeffs["x4"] * x4 + coeffs["x5"] * x5
    return max(0.0, merch_minutes), max(0.0, residue_minutes)


def estimate_micro_master_cycle_minutes(
    *,
    slope_distance_m: float,
    constant_minutes: float = MICRO_MASTER_DEFAULTS["constant_minutes"],
    outhaul_speed_m_per_s: float = MICRO_MASTER_DEFAULTS["outhaul_speed_m_per_s"],
    inhaul_speed_m_per_s: float = MICRO_MASTER_DEFAULTS["inhaul_speed_m_per_s"],
) -> float:
    """Total minutes per turn for the Model 9 Micro Master yarder (FERIC TN-54).

    Parameters
    ----------
    slope_distance_m : float
        Corridor distance (metres) between landing and stump.
    constant_minutes : float, default=MICRO_MASTER_DEFAULTS["constant_minutes"]
        Fixed time components per cycle (intercept from TN-54).
    outhaul_speed_m_per_s : float, default=MICRO_MASTER_DEFAULTS["outhaul_speed_m_per_s"]
        Line speed when travelling empty (m/s).
    inhaul_speed_m_per_s : float, default=MICRO_MASTER_DEFAULTS["inhaul_speed_m_per_s"]
        Line speed when hauling load (m/s).
    """

    if slope_distance_m <= 0:
        raise ValueError("Slope distance must be > 0 for the Micro Master regression")
    distance_minutes = (
        (slope_distance_m / outhaul_speed_m_per_s) + (slope_distance_m / inhaul_speed_m_per_s)
    ) / 60.0
    return constant_minutes + distance_minutes


def estimate_micro_master_productivity_m3_per_pmh(
    *,
    slope_distance_m: float,
    payload_m3: float | None = None,
    pieces_per_turn: float | None = None,
    piece_volume_m3: float | None = None,
) -> tuple[float, float, float, float, float]:
    """Productivity for the Model 9 Micro Master skyline (m³/PMH0).

    Parameters
    ----------
    slope_distance_m : float
        Corridor distance (metres).
    payload_m3 : float, optional
        Override payload per cycle (m³). When omitted the helper computes payload from
        ``pieces_per_turn`` × ``piece_volume_m3``.
    pieces_per_turn : float, optional
        Logs per cycle; defaults to TN-54 mean when omitted.
    piece_volume_m3 : float, optional
        Volume per log (m³); defaults to TN-54 mean when omitted.

    Returns
    -------
    tuple
        ``(productivity_m3_per_pmh, cycle_minutes, pieces, piece_volume, payload_m3)`` for reporting.
    """

    resolved_pieces = pieces_per_turn or MICRO_MASTER_DEFAULTS["pieces_per_turn"]
    resolved_piece_volume = piece_volume_m3 or MICRO_MASTER_DEFAULTS["piece_volume_m3"]
    if resolved_pieces <= 0:
        raise ValueError("Pieces per turn must be > 0 for the Micro Master regression")
    if resolved_piece_volume <= 0:
        raise ValueError("Piece volume must be > 0 for the Micro Master regression")
    resolved_payload = payload_m3 if payload_m3 is not None else resolved_pieces * resolved_piece_volume
    if resolved_payload <= 0:
        raise ValueError("Payload must be > 0 for the Micro Master regression")
    cycle_minutes = estimate_micro_master_cycle_minutes(slope_distance_m=slope_distance_m)
    productivity = (resolved_payload * 60.0) / cycle_minutes
    return productivity, cycle_minutes, resolved_pieces, resolved_piece_volume, resolved_payload


def estimate_hi_skid_cycle_minutes(
    *,
    slope_distance_m: float,
    constant_minutes: float = HI_SKID_DEFAULTS["constant_minutes"],
    line_speed_m_per_min: float = HI_SKID_DEFAULTS["line_speed_m_per_min"],
) -> float:
    """Minutes per yarding cycle for the Hi-Skid short-yard truck (FNG73).

    Parameters
    ----------
    slope_distance_m : float
        Yard/skid distance (metres) between landing and operational face.
    constant_minutes : float
        Fixed setup/hook time per cycle.
    line_speed_m_per_min : float
        Average line speed (metres/min) for both directions. Travel time assumes round trip.
    """

    if slope_distance_m <= 0:
        raise ValueError("Slope distance must be > 0 for the Hi-Skid regression")
    if line_speed_m_per_min <= 0:
        raise ValueError("Line speed must be > 0 for the Hi-Skid regression")
    travel_minutes = 2.0 * slope_distance_m / line_speed_m_per_min
    return constant_minutes + travel_minutes


def estimate_hi_skid_productivity_m3_per_pmh(
    *,
    slope_distance_m: float,
    include_travel_minutes: float | None = None,
    load_volume_m3: float | None = None,
    payload_per_cycle_m3: float | None = None,
    pieces_per_cycle: float | None = None,
    piece_volume_m3: float | None = None,
) -> tuple[float, float | None, float, float, float, float]:
    """Yarding productivity for the Hi-Skid short-yard truck (FNG73).

    Parameters
    ----------
    slope_distance_m : float
        Yard/skid distance (metres).
    include_travel_minutes : float, optional
        End-to-end travel/unload minutes for a full truck haul. When provided, overall productivity
        (including travel) is returned as the second element of the tuple.
    load_volume_m3 : float, optional
        Volume per truck load (m³) when calculating end-to-end productivity. Defaults to the FNG73
        12 m³ deck.
    payload_per_cycle_m3 : float, optional
        Payload per yard cycle (m³). Defaults to pieces × piece volume when omitted.
    pieces_per_cycle : float, optional
        Pieces per cycle; defaults to TN-54 observations.
    piece_volume_m3 : float, optional
        Volume per piece (m³); defaults to TN-54 observations.

    Returns
    -------
    tuple
        ``(yarding_productivity, overall_productivity, cycle_minutes, pieces_per_cycle, piece_volume_m3, payload_per_cycle_m3)``.
        ``overall_productivity`` is ``None`` when ``include_travel_minutes`` is omitted.
    """

    resolved_pieces = pieces_per_cycle or HI_SKID_DEFAULTS["pieces_per_cycle"]
    resolved_piece_volume = piece_volume_m3 or HI_SKID_DEFAULTS["piece_volume_m3"]
    if resolved_pieces <= 0:
        raise ValueError("Pieces per cycle must be > 0 for the Hi-Skid regression")
    if resolved_piece_volume <= 0:
        raise ValueError("Piece volume must be > 0 for the Hi-Skid regression")
    resolved_payload_cycle = (
        payload_per_cycle_m3
        if payload_per_cycle_m3 is not None
        else resolved_pieces * resolved_piece_volume
    )
    if resolved_payload_cycle <= 0:
        raise ValueError("Payload per cycle must be > 0 for the Hi-Skid regression")
    cycle_minutes = estimate_hi_skid_cycle_minutes(slope_distance_m=slope_distance_m)
    yarding_productivity = (resolved_payload_cycle * 60.0) / cycle_minutes

    overall_productivity = None
    if include_travel_minutes is not None and include_travel_minutes >= 0:
        resolved_load_volume = (
            load_volume_m3 if load_volume_m3 is not None else HI_SKID_DEFAULTS["payload_per_load_m3"]
        )
        if resolved_load_volume <= 0:
            raise ValueError("Load volume must be > 0 for Hi-Skid travel calculations")
        hours_to_fill_load = resolved_load_volume / yarding_productivity
        total_cycle_hours = hours_to_fill_load + include_travel_minutes / 60.0
        overall_productivity = resolved_load_volume / total_cycle_hours

    return (
        yarding_productivity,
        overall_productivity,
        cycle_minutes,
        resolved_pieces,
        resolved_piece_volume,
        resolved_payload_cycle,
    )


__all__ = [
    "estimate_cable_skidding_productivity_unver_spss",
    "estimate_cable_skidding_productivity_unver_robust",
    "estimate_cable_skidding_productivity_unver_spss_profile",
    "estimate_cable_skidding_productivity_unver_robust_profile",
    "estimate_cable_yarder_productivity_lee2018_uphill",
    "estimate_cable_yarder_productivity_lee2018_downhill",
    "estimate_cable_yarder_cycle_time_tr125_single_span",
    "estimate_cable_yarder_productivity_tr125_single_span",
    "estimate_cable_yarder_cycle_time_tr125_multi_span",
    "estimate_cable_yarder_productivity_tr125_multi_span",
    "estimate_cable_yarder_cycle_time_tr127_minutes",
    "estimate_cable_yarder_productivity_tr127",
    "estimate_standing_skyline_turn_time_aubuchon1979",
    "estimate_standing_skyline_productivity_aubuchon1979",
    "estimate_running_skyline_cycle_time_mcneel2000_minutes",
    "estimate_running_skyline_productivity_mcneel2000",
    "Fncy12ProductivityVariant",
    "Fncy12ProductivityResult",
    "estimate_tmy45_productivity_fncy12",
    "running_skyline_variant_defaults",
    "estimate_residue_cycle_time_ledoux_minutes",
    "estimate_residue_productivity_ledoux_m3_per_pmh",
    "ledoux_delay_component_minutes",
    "estimate_micro_master_cycle_minutes",
    "estimate_micro_master_productivity_m3_per_pmh",
    "estimate_hi_skid_cycle_minutes",
    "estimate_hi_skid_productivity_m3_per_pmh",
    "HI_SKID_DEFAULTS",
    "get_tn173_system",
    "list_tn173_system_ids",
    "HelicopterLonglineModel",
    "HelicopterProductivityResult",
    "estimate_helicopter_longline_productivity",
]
