from __future__ import annotations

import pytest

from fhops.productivity.stoilov2021 import (
    estimate_skidder_harvester_productivity_delay_free,
    estimate_skidder_harvester_productivity_with_delays,
)


def test_delay_free_productivity_basic() -> None:
    value = estimate_skidder_harvester_productivity_delay_free(
        skidding_distance_m=70, trees_per_cycle=2
    )
    assert value == pytest.approx(9.01, rel=1e-6)


def test_delay_free_productivity_clipped() -> None:
    value = estimate_skidder_harvester_productivity_delay_free(
        skidding_distance_m=500, trees_per_cycle=5
    )
    assert value == 0.0


def test_productivity_with_delays() -> None:
    value = estimate_skidder_harvester_productivity_with_delays(skidding_distance_m=69)
    assert value == pytest.approx(10.209, rel=1e-6)
