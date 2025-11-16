"""Grapple yarder productivity helpers calibrated on BC coastal datasets."""

from __future__ import annotations


def _validate_inputs(turn_volume_m3: float, yarding_distance_m: float) -> None:
    if turn_volume_m3 <= 0:
        raise ValueError("turn_volume_m3 must be > 0")
    if yarding_distance_m < 0:
        raise ValueError("yarding_distance_m must be >= 0")


def _minutes_per_turn_sr54(turn_volume_m3: float, yarding_distance_m: float) -> float:
    """Return cycle time (minutes/turn) for MacDonald (1988) Grapple 1 regression.

    Outhaul + inhaul comes from Table 9 in SR-54:
        time = 0.25 + distance * (0.00455 + 0.00030 * V)
    A fixed 1.35 min (hook/unhook/deck + moves + minor delays) is included per Table 10.
    """

    return 1.60 + yarding_distance_m * (0.00455 + 0.00030 * turn_volume_m3)


def _minutes_per_turn_tr75(
    yarding_distance_m: float,
    *,
    fixed_time_min: float,
    outhaul_intercept_min: float,
    outhaul_distance_coeff: float,
    inhaul_intercept_min: float,
    inhaul_distance_coeff: float,
) -> float:
    return (
        fixed_time_min
        + outhaul_intercept_min
        + outhaul_distance_coeff * yarding_distance_m
        + inhaul_intercept_min
        + inhaul_distance_coeff * yarding_distance_m
    )


def _productivity(turn_volume_m3: float, cycle_time_min: float) -> float:
    # Convert cycle time to hours and divide volume per turn.
    return 60.0 * turn_volume_m3 / cycle_time_min


def estimate_grapple_yarder_productivity_sr54(
    turn_volume_m3: float, yarding_distance_m: float
) -> float:
    """Estimate productivity (m³/PMH) for Washington 118A yarder on mechanically bunched wood.

    Derived from MacDonald (1988) SR-54, Table 9 and Table 10. Includes average move/minor delays.
    """

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    cycle_time = _minutes_per_turn_sr54(turn_volume_m3, yarding_distance_m)
    return _productivity(turn_volume_m3, cycle_time)


def estimate_grapple_yarder_productivity_tr75_bunched(
    turn_volume_m3: float, yarding_distance_m: float
) -> float:
    """Estimate productivity for Madill 084 swing yarder on mechanically bunched second-growth.

    Regression coefficients from Peterson (1987) TR-75, Table 6.
    """

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    cycle_time = _minutes_per_turn_tr75(
        yarding_distance_m,
        fixed_time_min=0.69,
        outhaul_intercept_min=0.0296,
        outhaul_distance_coeff=0.0027,
        inhaul_intercept_min=0.0,
        inhaul_distance_coeff=0.0044,
    )
    return _productivity(turn_volume_m3, cycle_time)


def estimate_grapple_yarder_productivity_tr75_handfelled(
    turn_volume_m3: float, yarding_distance_m: float
) -> float:
    """Estimate productivity for Madill 084 swing yarder on hand-felled second-growth timber."""

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    cycle_time = _minutes_per_turn_tr75(
        yarding_distance_m,
        fixed_time_min=0.74,
        outhaul_intercept_min=0.0323,
        outhaul_distance_coeff=0.0026,
        inhaul_intercept_min=0.0247,
        inhaul_distance_coeff=0.0035,
    )
    return _productivity(turn_volume_m3, cycle_time)


__all__ = [
    "estimate_grapple_yarder_productivity_sr54",
    "estimate_grapple_yarder_productivity_tr75_bunched",
    "estimate_grapple_yarder_productivity_tr75_handfelled",
]
