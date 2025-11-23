from __future__ import annotations

import pytest

from fhops.productivity.harvester_ctl import (
    ADV6N10HarvesterInputs,
    TN292HarvesterInputs,
    estimate_harvester_productivity_adv5n30,
    estimate_harvester_productivity_adv6n10,
    estimate_harvester_productivity_tn292,
    estimate_harvester_productivity_kellogg1994,
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


def test_adv5n30_base_and_brushed() -> None:
    base = estimate_harvester_productivity_adv5n30(removal_fraction=0.5)
    assert base == pytest.approx(19.0, rel=1e-6)
    brushed = estimate_harvester_productivity_adv5n30(removal_fraction=0.5, brushed=True)
    assert brushed == pytest.approx(19.0 * 1.21, rel=1e-6)


def test_adv5n30_interpolates_between_points() -> None:
    # halfway between 0.5 (19) and 0.7 (23) should be 21.
    value = estimate_harvester_productivity_adv5n30(removal_fraction=0.6)
    assert value == pytest.approx(21.0, rel=1e-6)


def test_tn292_pre_density_case() -> None:
    inputs = TN292HarvesterInputs(
        stem_volume_m3=0.12, stand_density_per_ha=1500, density_basis="pre"
    )
    result = estimate_harvester_productivity_tn292(inputs)
    assert result == pytest.approx(18.73, rel=5e-3)


def test_tn292_post_density_case() -> None:
    inputs = TN292HarvesterInputs(
        stem_volume_m3=0.12, stand_density_per_ha=1500, density_basis="post"
    )
    result = estimate_harvester_productivity_tn292(inputs)
    assert result == pytest.approx(22.27, rel=5e-3)


def test_kellogg1994_linear_regression() -> None:
    value = estimate_harvester_productivity_kellogg1994(dbh_cm=23.0)
    assert value == pytest.approx(-17.48 + 2.11 * 23.0, rel=1e-6)
