from __future__ import annotations

import pytest

from fhops.productivity.sessions2006 import (
    ShovelLoggingParameters,
    estimate_shovel_logging_productivity,
)


def test_sessions2006_pass_four_matches_published_spacing() -> None:
    params = ShovelLoggingParameters()
    result = estimate_shovel_logging_productivity(passes=4, params=params)
    assert result.road_spacing_m == pytest.approx(161.5, rel=1e-6)
    assert result.daily_volume_tonnes == pytest.approx(516.3260100969, rel=1e-6)
    assert result.cost_per_tonne == pytest.approx(2.9623129613, rel=1e-6)
    assert result.productivity_tonnes_per_pmh == pytest.approx(64.5407512621, rel=1e-6)
