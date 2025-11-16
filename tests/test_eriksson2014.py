from __future__ import annotations

import pytest

from fhops.productivity.eriksson2014 import (
    estimate_forwarder_productivity_final_felling,
    estimate_forwarder_productivity_thinning,
)


def test_forwarder_productivity_final_felling_example() -> None:
    value = estimate_forwarder_productivity_final_felling(
        mean_extraction_distance_m=300,
        mean_stem_size_m3=0.25,
        load_capacity_m3=14,
    )
    assert value == pytest.approx(20.9576546306, rel=1e-3)


def test_forwarder_productivity_thinning_example() -> None:
    value = estimate_forwarder_productivity_thinning(
        mean_extraction_distance_m=300,
        mean_stem_size_m3=0.15,
        load_capacity_m3=12,
    )
    assert value == pytest.approx(14.7539962472, rel=1e-3)
