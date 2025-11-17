"""Cable logging productivity helpers (Ünver-Okan 2020; Lee et al. 2018; TR125/TR127)."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from fhops.reference import get_appendix5_profile


_FEET_PER_METER = 3.28084


_RUNNING_SKYLINE_VARIANTS = {
    "yarder_a": {"pieces_per_cycle": 2.8, "piece_volume_m3": 2.5, "z1": 0.0},
    "yarder_b": {"pieces_per_cycle": 3.0, "piece_volume_m3": 1.6, "z1": 1.0},
}


def _validate_inputs(log_volume_m3: float, route_slope_percent: float) -> None:
    if log_volume_m3 <= 0:
        raise ValueError("log_volume_m3 must be > 0")
    if route_slope_percent <= 0:
        raise ValueError("route_slope_percent must be > 0")


def estimate_cable_skidding_productivity_unver_spss(
    log_volume_m3: float, route_slope_percent: float
) -> float:
    """Estimate productivity (m³/h) using the SPSS linear regression (Eq. 27)."""

    _validate_inputs(log_volume_m3, route_slope_percent)
    value = 4.188 + 5.325 * log_volume_m3 - 2.392 * route_slope_percent / 100.0
    return max(value, 0.0)


def estimate_cable_skidding_productivity_unver_robust(
    log_volume_m3: float, route_slope_percent: float
) -> float:
    """Estimate productivity (m³/h) using the robust regression (Eq. 28)."""

    _validate_inputs(log_volume_m3, route_slope_percent)
    value = 3.0940 + 5.5182 * log_volume_m3 - 1.3886 * route_slope_percent / 100.0
    return max(value, 0.0)


def _profile_slope_percent(profile: str) -> float:
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
    """Estimate productivity using a named Appendix 5 stand to supply slope (%)."""

    slope = _profile_slope_percent(profile)
    return estimate_cable_skidding_productivity_unver_spss(log_volume_m3, slope)


def estimate_cable_skidding_productivity_unver_robust_profile(
    *,
    profile: str,
    log_volume_m3: float,
) -> float:
    """Robust regression variant that derives slope (%) from an Appendix 5 stand."""

    slope = _profile_slope_percent(profile)
    return estimate_cable_skidding_productivity_unver_robust(log_volume_m3, slope)


def _validate_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _validate_non_negative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0")


def _m3_per_pmh(payload_m3: float, cycle_seconds: float) -> float:
    _validate_positive(payload_m3, "payload_m3")
    _validate_positive(cycle_seconds, "cycle_seconds")
    return payload_m3 * (3600.0 / cycle_seconds)


def _m3_per_pmh_from_minutes(payload_m3: float, cycle_minutes: float) -> float:
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


def estimate_cable_yarder_productivity_tr125_single_span(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    payload_m3: float = 1.6,
) -> float:
    """
    Estimate productivity (m³/PMH) for single-span skyline yarding (TR-125 Eq. 1).

    Parameters
    ----------
    slope_distance_m:
        Slope yarding distance (m). Regression calibrated for 10–350 m.
    lateral_distance_m:
        Lateral yarding distance (m). Regression calibrated for 0–50 m.
    payload_m3:
        Average payload per turn; TR-125 observed ≈1.6 m³ (3.4 logs × 0.47 m³/log).
    """

    _validate_positive(slope_distance_m, "slope_distance_m")
    _validate_positive(lateral_distance_m, "lateral_distance_m")
    cycle_minutes = 2.76140 + 0.00449 * slope_distance_m + 0.03750 * lateral_distance_m
    return _m3_per_pmh_from_minutes(payload_m3, cycle_minutes)


def estimate_cable_yarder_productivity_tr125_multi_span(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    payload_m3: float = 1.6,
) -> float:
    """
    Estimate productivity (m³/PMH) for multi-span skyline yarding (TR-125 Eq. 2).

    Parameters
    ----------
    slope_distance_m:
        Slope yarding distance (m). Regression calibrated for 10–420 m.
    lateral_distance_m:
        Lateral yarding distance (m). Regression calibrated for 0–50 m.
    payload_m3:
        Average payload per turn; TR-125 observed ≈1.6 m³.
    """

    _validate_positive(slope_distance_m, "slope_distance_m")
    _validate_positive(lateral_distance_m, "lateral_distance_m")
    cycle_minutes = 2.43108 + 0.00910 * slope_distance_m + 0.02563 * lateral_distance_m
    return _m3_per_pmh_from_minutes(payload_m3, cycle_minutes)


def _running_skyline_variant(key: str) -> dict[str, float]:
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
    """
    Estimate scheduled cycle time (minutes) for running skyline yarders (McNeel 2000).

    Source: McNeel, J.F. 2000. "Modeling Production of Longline Yarding Operations in
    Coastal British Columbia" (Journal of Forest Engineering 11(1):29–38) Table 4.
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
    """
    Estimate running skyline productivity (m³/PMH0) using McNeel (2000) regression.

    Parameters mirror Table 4 predictors: horizontal span, lateral yarding distance,
    deflection (vertical distance), and pieces per turn.
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
    LAMA = "lama"
    KMAX = "kmax"
    BELL_214B = "bell214b"
    S64E_AIRCRANE = "s64e_aircrane"


@dataclass(frozen=True)
class HelicopterSpec:
    model: HelicopterLonglineModel
    rated_payload_lb: float
    default_load_factor: float
    weight_to_volume_lb_per_m3: float
    hook_breakout_minutes: float
    unhook_minutes: float
    fly_empty_speed_mps: float
    fly_loaded_speed_mps: float

    @property
    def default_payload_lb(self) -> float:
        return self.rated_payload_lb * self.default_load_factor


_HELICOPTER_SPECS: dict[HelicopterLonglineModel, HelicopterSpec] = {
    HelicopterLonglineModel.LAMA: HelicopterSpec(
        model=HelicopterLonglineModel.LAMA,
        rated_payload_lb=2_500.0,
        default_load_factor=0.8,
        weight_to_volume_lb_per_m3=2_972.0,
        hook_breakout_minutes=0.8,
        unhook_minutes=0.15,
        fly_empty_speed_mps=22.0,
        fly_loaded_speed_mps=18.0,
    ),
    HelicopterLonglineModel.KMAX: HelicopterSpec(
        model=HelicopterLonglineModel.KMAX,
        rated_payload_lb=6_000.0,
        default_load_factor=0.75,
        weight_to_volume_lb_per_m3=2_972.0,
        hook_breakout_minutes=0.77,
        unhook_minutes=0.14,
        fly_empty_speed_mps=18.3,
        fly_loaded_speed_mps=13.6,
    ),
    HelicopterLonglineModel.BELL_214B: HelicopterSpec(
        model=HelicopterLonglineModel.BELL_214B,
        rated_payload_lb=8_000.0,
        default_load_factor=0.7,
        weight_to_volume_lb_per_m3=2_375.0,
        hook_breakout_minutes=1.1,
        unhook_minutes=0.28,
        fly_empty_speed_mps=23.5,
        fly_loaded_speed_mps=19.3,
    ),
    HelicopterLonglineModel.S64E_AIRCRANE: HelicopterSpec(
        model=HelicopterLonglineModel.S64E_AIRCRANE,
        rated_payload_lb=20_000.0,
        default_load_factor=0.7,
        weight_to_volume_lb_per_m3=2_700.0,
        hook_breakout_minutes=1.9,
        unhook_minutes=0.22,
        fly_empty_speed_mps=33.0,
        fly_loaded_speed_mps=27.0,
    ),
}


@dataclass(frozen=True)
class HelicopterProductivityResult:
    model: HelicopterLonglineModel
    flight_distance_m: float
    payload_lb: float
    payload_m3: float
    load_factor: float
    cycle_minutes: float
    turns_per_pmh0: float
    productivity_m3_per_pmh0: float
    additional_delay_minutes: float
    spec: HelicopterSpec


def _helicopter_spec(model: HelicopterLonglineModel) -> HelicopterSpec:
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
    """Estimate helicopter longline productivity (m³/PMH0) using FPInnovations case studies."""

    if flight_distance_m <= 0:
        raise ValueError("flight_distance_m must be > 0")
    if additional_delay_minutes < 0:
        raise ValueError("additional_delay_minutes must be >= 0")

    spec = _helicopter_spec(model)
    conversion = weight_to_volume_lb_per_m3 or spec.weight_to_volume_lb_per_m3

    if payload_m3 is not None and payload_m3 <= 0:
        raise ValueError("payload_m3 must be > 0 when specified.")
    if load_factor is not None and not (0.0 < load_factor <= 1.0):
        raise ValueError("load_factor must lie in (0, 1].")

    if payload_m3 is not None:
        payload_lb = payload_m3 * conversion
        load_factor_value = payload_lb / spec.rated_payload_lb
    else:
        load_factor_value = load_factor if load_factor is not None else spec.default_load_factor
        payload_lb = spec.rated_payload_lb * load_factor_value
        payload_m3 = payload_lb / conversion

    if load_factor_value <= 0 or payload_lb <= 0:
        raise ValueError("Computed payload is not positive; check inputs.")

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
        payload_lb=payload_lb,
        payload_m3=payload_m3,
        load_factor=load_factor_value,
        cycle_minutes=cycle_minutes,
        turns_per_pmh0=turns_per_hour,
        productivity_m3_per_pmh0=productivity,
        additional_delay_minutes=additional_delay_minutes,
        spec=spec,
    )


def estimate_standing_skyline_turn_time_aubuchon1979(
    *,
    slope_distance_m: float,
    lateral_distance_m: float,
    logs_per_turn: float,
    crew_size: float,
) -> float:
    """Delay-free turn time (min) from Hensel et al. (1979) compiled by Aubuchon (1982).

    Parameters use SI units for convenience but the regression was published in feet, so
    conversions are applied internally. Valid for uphill Wyssen standing skyline trials
    with slopes 45–75 %, 3.5–6 logs/turn, 1 000–3 000 ft slope distance, 50–150 ft lateral.
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
    """Estimate standing skyline productivity (m³/PMH0) via Aubuchon (1982) tables."""

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


def running_skyline_variant_defaults(yarder_variant: str) -> tuple[float, float]:
    """Return (pieces_per_cycle, piece_volume_m3) defaults for the given variant."""

    variant = _running_skyline_variant(yarder_variant)
    return variant["pieces_per_cycle"], variant["piece_volume_m3"]


@dataclass(frozen=True)
class _TR127Predictor:
    name: str
    units: str
    value_range: tuple[float, float]
    coefficient: float


@dataclass(frozen=True)
class _TR127Regression:
    block: int
    description: str
    intercept_minutes: float
    predictors: tuple[_TR127Predictor, ...]


_TR127_REGRESSIONS_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tr127_regressions.json"
)


@lru_cache(maxsize=1)
def _load_tr127_models() -> Mapping[int, _TR127Regression]:
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
) -> dict[str, float]:
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
        else:
            raise ValueError(f"Unsupported TR127 predictor '{predictor.name}'.")
    return values


def _warn_if_out_of_range(name: str, value: float, value_range: tuple[float, float]) -> None:
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
) -> float:
    """
    Estimate delay-free cycle time (minutes) using TR127 Appendix VII regressions.

    Parameters
    ----------
    block:
        Block identifier (1–6) corresponding to the published regression.
    slope_distance_m, lateral_distance_m, num_logs:
        Predictor values required by the chosen block model. Values outside the calibrated
        range will emit warnings but still be evaluated.
    """

    model = _load_tr127_models().get(block)
    if model is None:
        raise ValueError(f"Unknown TR127 block: {block}")
    values = _ensure_tr127_inputs(block, slope_distance_m, lateral_distance_m, num_logs)
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
) -> float:
    """
    Estimate TR127 skyline productivity (m³/PMH) using block-specific regressions.

    Parameters
    ----------
    block:
        Block identifier (1–6).
    payload_m3:
        Payload per turn. Defaults to 1.6 m³ when not specified in TR127.
    slope_distance_m, lateral_distance_m, num_logs:
        Predictors required by the chosen block. Supply only those listed in Appendix VII.
    """

    cycle_minutes = estimate_cable_yarder_cycle_time_tr127_minutes(
        block=block,
        slope_distance_m=slope_distance_m,
        lateral_distance_m=lateral_distance_m,
        num_logs=num_logs,
    )
    return _m3_per_pmh_from_minutes(payload_m3, cycle_minutes)


__all__ = [
    "estimate_cable_skidding_productivity_unver_spss",
    "estimate_cable_skidding_productivity_unver_robust",
    "estimate_cable_skidding_productivity_unver_spss_profile",
    "estimate_cable_skidding_productivity_unver_robust_profile",
    "estimate_cable_yarder_productivity_lee2018_uphill",
    "estimate_cable_yarder_productivity_lee2018_downhill",
    "estimate_standing_skyline_turn_time_aubuchon1979",
    "estimate_standing_skyline_productivity_aubuchon1979",
]
