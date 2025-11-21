from fhops.productivity.cable_logging import (
    estimate_cable_skidding_productivity_unver_robust,
    estimate_cable_skidding_productivity_unver_spss,
    estimate_hi_skid_productivity_m3_per_pmh,
    get_tn173_system,
    list_tn173_system_ids,
)


def test_unver_spss_matches_paper() -> None:
    prod = estimate_cable_skidding_productivity_unver_spss(
        log_volume_m3=0.5, route_slope_percent=30.0
    )
    assert abs(prod - (4.188 + 5.325 * 0.5 - 2.392 * 0.3)) < 1e-6


def test_unver_robust_positive() -> None:
    prod = estimate_cable_skidding_productivity_unver_robust(
        log_volume_m3=0.5, route_slope_percent=30.0
    )
    assert prod > 0


def test_tn173_system_loader() -> None:
    system_ids = list_tn173_system_ids()
    assert "tn173_ecologger" in system_ids
    system = get_tn173_system("tn173_ecologger")
    assert system.cycle_minutes > 0
    assert system.payload_m3 is not None and system.payload_m3 > 0


def test_hi_skid_matches_observed_rate() -> None:
    productivity, _, _, _, _, _ = estimate_hi_skid_productivity_m3_per_pmh(
        slope_distance_m=30.0
    )
    assert abs(productivity - 4.16) < 0.05
