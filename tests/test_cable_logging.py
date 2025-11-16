import math

import pytest

from fhops.productivity import (
    estimate_cable_skidding_productivity_unver_robust,
    estimate_cable_skidding_productivity_unver_robust_profile,
    estimate_cable_skidding_productivity_unver_spss,
    estimate_cable_skidding_productivity_unver_spss_profile,
    estimate_cable_yarder_productivity_lee2018_downhill,
    estimate_cable_yarder_productivity_lee2018_uphill,
    estimate_cable_yarder_productivity_tr125_multi_span,
    estimate_cable_yarder_productivity_tr125_single_span,
)


def test_unver_models_are_positive():
    assert estimate_cable_skidding_productivity_unver_spss(0.3, 25.0) > 0
    assert estimate_cable_skidding_productivity_unver_robust(0.3, 25.0) > 0


def test_lee2018_uphill_matches_case_study_mean():
    result = estimate_cable_yarder_productivity_lee2018_uphill(
        yarding_distance_m=55.0,
        payload_m3=0.57,
    )
    assert math.isclose(result, 9.04, rel_tol=0.06)


def test_lee2018_downhill_matches_case_study_mean():
    result = estimate_cable_yarder_productivity_lee2018_downhill(
        yarding_distance_m=53.0,
        lateral_distance_m=5.0,
        large_end_diameter_cm=34.0,
        payload_m3=0.61,
    )
    assert math.isclose(result, 7.87, rel_tol=0.07)


def test_lee2018_validates_inputs():
    with pytest.raises(ValueError):
        estimate_cable_yarder_productivity_lee2018_uphill(yarding_distance_m=-5.0)
    with pytest.raises(ValueError):
        estimate_cable_yarder_productivity_lee2018_downhill(
            yarding_distance_m=50.0,
            lateral_distance_m=0.0,
            large_end_diameter_cm=34.0,
        )


def test_unver_profile_helpers_match_manual_slope():
    profile = "Ackerman et al. (2018)"
    value_spss = estimate_cable_skidding_productivity_unver_spss_profile(
        profile=profile, log_volume_m3=0.35
    )
    manual = estimate_cable_skidding_productivity_unver_spss(0.35, 23.0)
    assert pytest.approx(value_spss, rel=1e-6) == manual
    value_robust = estimate_cable_skidding_productivity_unver_robust_profile(
        profile=profile, log_volume_m3=0.35
    )
    manual_robust = estimate_cable_skidding_productivity_unver_robust(0.35, 23.0)
    assert pytest.approx(value_robust, rel=1e-6) == manual_robust


def test_tr125_productivity_declines_with_distance():
    single_short = estimate_cable_yarder_productivity_tr125_single_span(
        slope_distance_m=100, lateral_distance_m=15
    )
    single_long = estimate_cable_yarder_productivity_tr125_single_span(
        slope_distance_m=250, lateral_distance_m=15
    )
    assert single_short > single_long
    multi = estimate_cable_yarder_productivity_tr125_multi_span(
        slope_distance_m=250, lateral_distance_m=25
    )
    assert multi < single_long
