from __future__ import annotations

import pytest

from fhops.productivity.harvester_ctl import (
    ADV6N10HarvesterInputs,
    estimate_harvester_productivity_adv6n10,
)


def test_adv6n10_harvester_regression_matches_formula() -> None:
    inputs = ADV6N10HarvesterInputs(
        stem_volume_m3=0.12,
        products_count=3.0,
        stems_per_cycle=1.4,
        mean_log_length_m=4.8,
    )
    result = estimate_harvester_productivity_adv6n10(inputs)
    assert result == pytest.approx(19.7413, rel=5e-3)
