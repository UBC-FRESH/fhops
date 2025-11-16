"""Brushwood harwarder productivity helper from Laitila & Väätäinen (2020)."""

from __future__ import annotations

import math


def estimate_brushwood_harwarder_productivity(
    harvested_trees_per_ha: float,
    average_tree_volume_dm3: float,
    forwarding_distance_m: float,
    *,
    harwarder_payload_m3: float = 7.1,
    grapple_load_unloading_m3: float = 0.29,
) -> float:
    """Estimate harwarder productivity (m^3/PMH) for roadside brushwood recovery.

    Parameters mirror the notation from Laitila & Väätäinen (2020):
    - harvested_trees_per_ha == x1 (trees/ha)
    - average_tree_volume_dm3 == x2 (dm^3/tree)
    - forwarding_distance_m == x5 (m, mean loaded/unloaded distance)
    - harwarder_payload_m3 == x6 (m^3/load), defaults to the 7.1 m^3 follow-up value
    - grapple_load_unloading_m3 == x4 (m^3/grapple), defaults to the 0.29 m^3 follow-up value
    """

    if harvested_trees_per_ha <= 0:
        raise ValueError("harvested_trees_per_ha must be > 0")
    if average_tree_volume_dm3 <= 0:
        raise ValueError("average_tree_volume_dm3 must be > 0")
    if forwarding_distance_m < 0:
        raise ValueError("forwarding_distance_m must be >= 0")
    if harwarder_payload_m3 <= 0:
        raise ValueError("harwarder_payload_m3 must be > 0")
    if grapple_load_unloading_m3 <= 0:
        raise ValueError("grapple_load_unloading_m3 must be > 0")

    x1 = harvested_trees_per_ha
    x2 = average_tree_volume_dm3
    x2_m3 = x2 / 1000.0

    t_moving = 0.168 + 4351.5 * (1.0 / x1)
    t_cutting = -4.571 + 3.4 * math.log(x2)
    trees_per_grapple = 1.163 + 53.675 * (1.0 / x2)
    grapple_load_loading_m3 = trees_per_grapple * x2_m3
    if grapple_load_loading_m3 <= 0:
        raise ValueError("derived grapple load during loading must be > 0")

    t_loading = -8.222 + 7.237 * (1.0 / grapple_load_loading_m3)
    t_unloading = 99.03 - 140.211 * grapple_load_unloading_m3 + 5.4
    t_forwarding = 24.154 + 0.691 * forwarding_distance_m

    seconds_per_m3_from_tree_based_terms = (t_moving + t_cutting) * (1000.0 / x2)
    seconds_per_m3_from_loading = t_loading + t_unloading
    seconds_per_m3_from_forwarding = (2.0 * t_forwarding) / harwarder_payload_m3

    total_seconds_per_m3 = (
        seconds_per_m3_from_tree_based_terms
        + seconds_per_m3_from_loading
        + seconds_per_m3_from_forwarding
    )

    if total_seconds_per_m3 <= 0:
        raise ValueError("derived total seconds per m3 must be > 0")

    return 3600.0 / total_seconds_per_m3


__all__ = ["estimate_brushwood_harwarder_productivity"]
