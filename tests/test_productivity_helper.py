import math

import numpy as np
import pytest

from fhops.productivity import (
    LahrsenModel,
    estimate_productivity,
    estimate_productivity_distribution,
    load_lahrsen_ranges,
)
from fhops.core import FHOPSValueError


def test_estimate_productivity_matches_coefficients():
    result = estimate_productivity(
        avg_stem_size=0.4,
        volume_per_ha=300.0,
        stem_density=900.0,
        ground_slope=15.0,
        model=LahrsenModel.DAILY,
    )
    expected = (
        67.99345 * 0.4
        + 0.05943 * 300.0
        + 0.01236 * 900.0
        - 0.46146 * 15.0
    )
    assert math.isclose(result.predicted_m3_per_pmh, expected, rel_tol=1e-9)


def test_validation_range_guard():
    with pytest.raises(FHOPSValueError):
        estimate_productivity(
            avg_stem_size=2.0,
            volume_per_ha=300.0,
            stem_density=900.0,
            ground_slope=15.0,
        )


def test_load_lahrsen_ranges_contains_expected_keys():
    ranges = load_lahrsen_ranges()
    assert "daily" in ranges and "cutblock" in ranges
    daily = ranges["daily"]
    assert daily["avg_stem_size_m3"]["min"] == pytest.approx(0.09)
    assert ranges["cutblock"]["productivity_m3_per_pmh15"]["max"] == pytest.approx(133.1)


def test_allow_out_of_range_collects_warnings():
    result = estimate_productivity(
        avg_stem_size=2.0,
        volume_per_ha=300.0,
        stem_density=900.0,
        ground_slope=15.0,
        validate_ranges=False,
    )
    assert result.out_of_range


def test_monte_carlo_distribution_matches_deterministic_mean():
    np.random.seed(123)
    result = estimate_productivity_distribution(
        avg_stem_size_mu=0.4,
        avg_stem_size_sigma=0.0,
        volume_per_ha_mu=320.0,
        volume_per_ha_sigma=0.0,
        stem_density_mu=900.0,
        stem_density_sigma=0.0,
        ground_slope_mu=18.0,
        ground_slope_sigma=0.0,
        model=LahrsenModel.DAILY,
        method="monte-carlo",
        samples=10,
    )
    deterministic = estimate_productivity(
        avg_stem_size=0.4,
        volume_per_ha=320.0,
        stem_density=900.0,
        ground_slope=18.0,
    )
    assert pytest.approx(result.expected_m3_per_pmh, rel=1e-6) == deterministic.predicted_m3_per_pmh
