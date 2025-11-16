"""Cable logging productivity helpers (Ünver-Okan 2020)."""

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


__all__ = [
    "estimate_cable_skidding_productivity_unver_spss",
    "estimate_cable_skidding_productivity_unver_robust",
]
