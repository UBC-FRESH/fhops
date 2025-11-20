from __future__ import annotations

import math

import pytest

from fhops.productivity.grapple_bc import (
    estimate_grapple_yarder_productivity_adv5n28,
    estimate_grapple_yarder_productivity_sr54,
    estimate_grapple_yarder_productivity_tr75_bunched,
    estimate_grapple_yarder_productivity_tr75_handfelled,
    estimate_grapple_yarder_productivity_tn157,
    estimate_grapple_yarder_productivity_tn147,
    estimate_grapple_yarder_productivity_tr122,
    get_tn157_case,
    get_tn147_case,
    get_tr122_treatment,
    get_adv5n28_block,
)


def test_sr54_matches_report_curve() -> None:
    # 100 m yarding distance, 3 m³ turn volume (approx. Figure O).
    prod = estimate_grapple_yarder_productivity_sr54(turn_volume_m3=3.0, yarding_distance_m=100.0)
    assert math.isclose(prod, 83.9, rel_tol=0.02)


def test_tr75_bunched_cycle_matches_table() -> None:
    prod = estimate_grapple_yarder_productivity_tr75_bunched(
        turn_volume_m3=0.9, yarding_distance_m=50.0
    )
    # Table 6 reports ~1.08 min/turn at 50 m => ~50 m³/PMH for 0.9 m³ turns.
    assert math.isclose(prod, 50.0, rel_tol=0.05)


def test_tr75_handfelled_slower_cycle() -> None:
    prod = estimate_grapple_yarder_productivity_tr75_handfelled(
        turn_volume_m3=0.9, yarding_distance_m=50.0
    )
    assert prod < estimate_grapple_yarder_productivity_tr75_bunched(0.9, 50.0)
    assert math.isclose(prod, 49.0, rel_tol=0.05)


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        estimate_grapple_yarder_productivity_sr54(turn_volume_m3=-1.0, yarding_distance_m=50.0)
    with pytest.raises(ValueError):
        estimate_grapple_yarder_productivity_tr75_bunched(
            turn_volume_m3=1.0, yarding_distance_m=-5.0
        )


def test_tn157_combined_productivity_matches_case() -> None:
    case = get_tn157_case("combined")
    prod = estimate_grapple_yarder_productivity_tn157()
    assert math.isclose(prod, case.productivity_m3_per_pmh, rel_tol=1e-9)


def test_tn157_invalid_case() -> None:
    with pytest.raises(ValueError):
        get_tn157_case("case99")


def test_tn147_combined_productivity_matches_case() -> None:
    case = get_tn147_case("combined")
    prod = estimate_grapple_yarder_productivity_tn147()
    assert math.isclose(prod, case.productivity_m3_per_pmh, rel_tol=1e-9)


def test_tr122_clearcut_productivity_matches_dataset() -> None:
    treatment = get_tr122_treatment("clearcut")
    prod = estimate_grapple_yarder_productivity_tr122("clearcut")
    assert math.isclose(prod, treatment.productivity_m3_per_pmh, rel_tol=1e-9)


def test_adv5n28_clearcut_matches_dataset() -> None:
    block_id = "block_1_clearcut_with_reserves"
    block = get_adv5n28_block(block_id)
    prod = estimate_grapple_yarder_productivity_adv5n28(block_id)
    assert math.isclose(prod, block.productivity_m3_per_pmh, rel_tol=1e-9)


def test_adv5n28_invalid_block() -> None:
    with pytest.raises(ValueError):
        get_adv5n28_block("not-a-block")
