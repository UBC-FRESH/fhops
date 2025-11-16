from __future__ import annotations

import pytest

from fhops.productivity.ghaffariyan2019 import (
    estimate_forwarder_productivity_large_forwarder_thinning,
    estimate_forwarder_productivity_small_forwarder_thinning,
)


@pytest.mark.parametrize(
    ("distance_m", "expected_small", "expected_large"),
    [
        (100.0, 31.8, 49.1),
        (400.0, 28.1, 41.2),
    ],
)
def test_forwarder_productivity_matches_table(distance_m: float, expected_small: float, expected_large: float) -> None:
    assert estimate_forwarder_productivity_small_forwarder_thinning(distance_m) == pytest.approx(expected_small, rel=5e-3)
    assert estimate_forwarder_productivity_large_forwarder_thinning(distance_m) == pytest.approx(expected_large, rel=5e-3)


def test_forwarder_productivity_applies_slope_factor() -> None:
    baseline = estimate_forwarder_productivity_small_forwarder_thinning(200.0)
    assert estimate_forwarder_productivity_small_forwarder_thinning(200.0, slope_factor=0.75) == pytest.approx(baseline * 0.75)
