from __future__ import annotations

import math

import pytest

from fhops.productivity import ALPACASlopeClass
from fhops.productivity.laitila2020 import estimate_brushwood_harwarder_productivity
from fhops.productivity.forwarder_bc import (
    ForwarderBCModel,
    estimate_forwarder_productivity_bc,
)


@pytest.mark.parametrize(
    ("model", "distance_m", "expected"),
    [
        (ForwarderBCModel.GHAFFARIYAN_SMALL, 100.0, 31.8),
        (ForwarderBCModel.GHAFFARIYAN_LARGE, 100.0, 49.1),
        (ForwarderBCModel.GHAFFARIYAN_SMALL, 400.0, 28.1),
        (ForwarderBCModel.GHAFFARIYAN_LARGE, 400.0, 41.2),
    ],
)
def test_forwarder_bc_ghaffariyan_matches_tables(
    model: ForwarderBCModel, distance_m: float, expected: float
) -> None:
    result = estimate_forwarder_productivity_bc(
        model=model,
        extraction_distance_m=distance_m,
        slope_class=ALPACASlopeClass.FLAT,
    )
    assert result.predicted_m3_per_pmh == pytest.approx(expected, rel=5e-3)


def test_forwarder_bc_kellogg_matches_table8() -> None:
    result = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.KELLOGG_MIXED,
        volume_per_load_m3=9.3,
        distance_out_m=274.0,
        travel_in_unit_m=76.0,
        distance_in_m=259.0,
    )
    assert result.predicted_m3_per_pmh == pytest.approx(13.4, rel=1e-2)


def test_forwarder_bc_adv6n10_regression() -> None:
    result = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.ADV6N10_SHORTWOOD,
        payload_m3=10.0,
        mean_log_length_m=5.0,
        travel_speed_m_per_min=40.0,
        trail_length_m=300.0,
        products_per_trail=2.0,
    )
    assert result.predicted_m3_per_pmh == pytest.approx(22.21, rel=5e-3)


def test_forwarder_bc_eriksson_final_felling() -> None:
    result = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.ERIKSSON_FINAL_FELLING,
        mean_extraction_distance_m=300.0,
        mean_stem_size_m3=0.25,
        load_capacity_m3=14.0,
    )
    assert result.predicted_m3_per_pmh == pytest.approx(20.9576546306, rel=1e-3)


def test_forwarder_bc_eriksson_thinning() -> None:
    result = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.ERIKSSON_THINNING,
        mean_extraction_distance_m=300.0,
        mean_stem_size_m3=0.15,
        load_capacity_m3=12.0,
    )
    assert result.predicted_m3_per_pmh == pytest.approx(14.7539962472, rel=1e-3)


def test_forwarder_bc_adv1n12_regression() -> None:
    distance = 400.0
    result = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.ADV1N12_SHORTWOOD,
        extraction_distance_m=distance,
    )
    expected = 8.4438 * math.exp(-0.004 * distance)
    assert result.predicted_m3_per_pmh == pytest.approx(expected, rel=1e-6)


def test_forwarder_bc_brushwood_matches_helper() -> None:
    expected = estimate_brushwood_harwarder_productivity(
        harvested_trees_per_ha=1500,
        average_tree_volume_dm3=45.0,
        forwarding_distance_m=200.0,
    )
    result = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.LAITILA_VAATAINEN_BRUSHWOOD,
        harvested_trees_per_ha=1500,
        average_tree_volume_dm3=45.0,
        forwarding_distance_m=200.0,
    )
    assert result.predicted_m3_per_pmh == pytest.approx(expected, rel=1e-5)
