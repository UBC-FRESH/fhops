from __future__ import annotations

import pytest

from fhops.productivity.laitila2020 import estimate_brushwood_harwarder_productivity


@pytest.mark.parametrize(
    ("avg_tree_volume_dm3", "forwarding_distance_m", "expected"),
    [
        (15.0, 100.0, 6.5192056855),
        (15.0, 400.0, 5.8957544119),
        (30.0, 100.0, 8.4426399646),
        (30.0, 400.0, 7.4257230621),
    ],
)
def test_laitila2020_matches_reported_productivity(avg_tree_volume_dm3: float, forwarding_distance_m: float, expected: float) -> None:
    value = estimate_brushwood_harwarder_productivity(
        harvested_trees_per_ha=6000.0,
        average_tree_volume_dm3=avg_tree_volume_dm3,
        forwarding_distance_m=forwarding_distance_m,
    )
    assert value == pytest.approx(expected, rel=1e-6)
