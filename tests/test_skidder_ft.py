from __future__ import annotations

import pytest

from fhops.productivity.skidder_ft import (
    Han2018SkidderMethod,
    TrailSpacingPattern,
    DeckingCondition,
    estimate_grapple_skidder_productivity_han2018,
)


def test_han2018_lop_and_scatter_cycle_time() -> None:
    result = estimate_grapple_skidder_productivity_han2018(
        method=Han2018SkidderMethod.LOP_AND_SCATTER,
        pieces_per_cycle=20.0,
        piece_volume_m3=0.25,
        empty_distance_m=150.0,
        loaded_distance_m=130.0,
    )
    assert result.cycle_time_seconds == pytest.approx(213.279, rel=1e-6)
    assert result.predicted_m3_per_pmh == pytest.approx(84.401, rel=1e-3)


def test_han2018_whole_tree_cycle_time() -> None:
    result = estimate_grapple_skidder_productivity_han2018(
        method=Han2018SkidderMethod.WHOLE_TREE,
        pieces_per_cycle=18.0,
        piece_volume_m3=0.35,
        empty_distance_m=160.0,
        loaded_distance_m=140.0,
    )
    assert result.cycle_time_seconds == pytest.approx(25.125 + (1.881 * 18) + (0.632 * 160) + (0.477 * 140), rel=1e-9)
    assert result.predicted_m3_per_pmh > 0


def test_han2018_with_trail_and_decking_multipliers() -> None:
    baseline = estimate_grapple_skidder_productivity_han2018(
        method=Han2018SkidderMethod.WHOLE_TREE,
        pieces_per_cycle=18.0,
        piece_volume_m3=0.35,
        empty_distance_m=160.0,
        loaded_distance_m=140.0,
    )
    adjusted = estimate_grapple_skidder_productivity_han2018(
        method=Han2018SkidderMethod.WHOLE_TREE,
        pieces_per_cycle=18.0,
        piece_volume_m3=0.35,
        empty_distance_m=160.0,
        loaded_distance_m=140.0,
        trail_pattern=TrailSpacingPattern.NARROW_13_15M,
        decking_condition=DeckingCondition.CONSTRAINED,
    )
    assert adjusted.predicted_m3_per_pmh < baseline.predicted_m3_per_pmh
