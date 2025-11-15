import math

import pytest

from fhops.productivity import LahrsenModel, estimate_productivity
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
