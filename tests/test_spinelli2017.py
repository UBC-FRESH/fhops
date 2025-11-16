from __future__ import annotations

import pytest

from fhops.productivity.spinelli2017 import (
    GrappleYarderInputs,
    estimate_grapple_yarder_productivity,
)


def test_spinelli2017_heavy_yarder_matches_reported_range() -> None:
    inputs = GrappleYarderInputs(
        piece_volume_m3=0.5,
        pieces_per_load=4.1,
        line_length_m=100.0,
        stacking_distance_m=20.0,
        yarder_type="heavy",
    )
    value = estimate_grapple_yarder_productivity(inputs)
    assert value == pytest.approx(58.9772, rel=1e-6)


def test_spinelli2017_medium_yarder_interaction_term() -> None:
    volume = 0.4
    pieces = 6.88 - 2.73 * volume
    inputs = GrappleYarderInputs(
        piece_volume_m3=volume,
        pieces_per_load=pieces,
        line_length_m=100.0,
        stacking_distance_m=20.0,
        yarder_type="medium",
    )
    value = estimate_grapple_yarder_productivity(inputs)
    assert value == pytest.approx(59.654336, rel=1e-6)
