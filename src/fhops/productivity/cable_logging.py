"""Cable logging productivity helpers (Ünver-Okan 2020; Lee et al. 2018; TR125/TR127)."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fhops.reference import get_appendix5_profile


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
]
