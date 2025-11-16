from fhops.productivity.cable_logging import (
    estimate_cable_skidding_productivity_unver_robust,
    estimate_cable_skidding_productivity_unver_spss,
)


def test_unver_spss_matches_paper() -> None:
    prod = estimate_cable_skidding_productivity_unver_spss(log_volume_m3=0.5, route_slope_percent=30.0)
    assert abs(prod - (4.188 + 5.325 * 0.5 - 2.392 * 0.3)) < 1e-6


def test_unver_robust_positive() -> None:
    prod = estimate_cable_skidding_productivity_unver_robust(log_volume_m3=0.5, route_slope_percent=30.0)
    assert prod > 0

