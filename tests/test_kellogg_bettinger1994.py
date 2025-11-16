from __future__ import annotations

import pytest

from fhops.productivity.kellogg_bettinger1994 import (
    LoadType,
    estimate_forwarder_productivity_kellogg_bettinger,
)


@pytest.mark.parametrize(
    ("load_type", "volume_per_load_m3", "expected"),
    [
        (LoadType.SAWLOG, 9.9, 15.3),
        (LoadType.PULPWOOD, 5.7, 10.7),
        (LoadType.MIXED, 9.3, 13.4),
    ],
)
def test_kellogg_forwarder_matches_table8(load_type: LoadType, volume_per_load_m3: float, expected: float) -> None:
    value = estimate_forwarder_productivity_kellogg_bettinger(
        load_type=load_type,
        volume_per_load_m3=volume_per_load_m3,
        distance_out_m=274.0,
        travel_in_unit_m=76.0,
        distance_in_m=259.0,
    )
    assert value == pytest.approx(expected, rel=1e-2)
