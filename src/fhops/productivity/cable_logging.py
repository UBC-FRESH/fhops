"""Cable logging productivity helpers (Ünver-Okan 2020; Lee et al. 2018)."""

from __future__ import annotations


def _validate_inputs(log_volume_m3: float, route_slope_percent: float) -> None:
    if log_volume_m3 <= 0:
        raise ValueError("log_volume_m3 must be > 0")
    if route_slope_percent <= 0:
        raise ValueError("route_slope_percent must be > 0")


def estimate_cable_skidding_productivity_unver_spss(log_volume_m3: float, route_slope_percent: float) -> float:
    """Estimate productivity (m³/h) using the SPSS linear regression (Eq. 27)."""

    _validate_inputs(log_volume_m3, route_slope_percent)
    value = 4.188 + 5.325 * log_volume_m3 - 2.392 * route_slope_percent / 100.0
    return max(value, 0.0)


def estimate_cable_skidding_productivity_unver_robust(log_volume_m3: float, route_slope_percent: float) -> float:
    """Estimate productivity (m³/h) using the robust regression (Eq. 28)."""

    _validate_inputs(log_volume_m3, route_slope_percent)
    value = 3.0940 + 5.5182 * log_volume_m3 - 1.3886 * route_slope_percent / 100.0
    return max(value, 0.0)


def _validate_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _m3_per_pmh(payload_m3: float, cycle_seconds: float) -> float:
    _validate_positive(payload_m3, "payload_m3")
    _validate_positive(cycle_seconds, "cycle_seconds")
    return payload_m3 * (3600.0 / cycle_seconds)


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


__all__ = [
    "estimate_cable_skidding_productivity_unver_spss",
    "estimate_cable_skidding_productivity_unver_robust",
    "estimate_cable_yarder_productivity_lee2018_uphill",
    "estimate_cable_yarder_productivity_lee2018_downhill",
]
