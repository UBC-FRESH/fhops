import math

import numpy as np
import pytest

from fhops.core import FHOPSValueError
from fhops.productivity import (
    LahrsenModel,
    estimate_productivity,
    estimate_productivity_distribution,
    estimate_processor_productivity_labelle2016,
    estimate_processor_productivity_labelle2017,
    estimate_processor_productivity_labelle2018,
    estimate_processor_productivity_labelle2019_dbh,
    estimate_processor_productivity_labelle2019_volume,
    estimate_processor_productivity_visser2015,
    get_labelle_huss_automatic_bucking_adjustment,
    load_lahrsen_ranges,
)


def test_estimate_productivity_matches_coefficients():
    result = estimate_productivity(
        avg_stem_size=0.4,
        volume_per_ha=300.0,
        stem_density=900.0,
        ground_slope=15.0,
        model=LahrsenModel.DAILY,
    )
    expected = 67.99345 * 0.4 + 0.05943 * 300.0 + 0.01236 * 900.0 - 0.46146 * 15.0
    assert math.isclose(result.predicted_m3_per_pmh, expected, rel_tol=1e-9)


def test_validation_range_guard():
    with pytest.raises(FHOPSValueError):
        estimate_productivity(
            avg_stem_size=2.0,
            volume_per_ha=300.0,
            stem_density=900.0,
            ground_slope=15.0,
        )


def test_load_lahrsen_ranges_contains_expected_keys():
    ranges = load_lahrsen_ranges()
    assert "daily" in ranges and "cutblock" in ranges
    daily = ranges["daily"]
    assert daily["avg_stem_size_m3"]["min"] == pytest.approx(0.09)
    assert ranges["cutblock"]["productivity_m3_per_pmh15"]["max"] == pytest.approx(133.1)


def test_allow_out_of_range_collects_warnings():
    result = estimate_productivity(
        avg_stem_size=2.0,
        volume_per_ha=300.0,
        stem_density=900.0,
        ground_slope=15.0,
        validate_ranges=False,
    )
    assert result.out_of_range


def test_monte_carlo_distribution_matches_deterministic_mean():
    np.random.seed(123)
    result = estimate_productivity_distribution(
        avg_stem_size_mu=0.4,
        avg_stem_size_sigma=0.0,
        volume_per_ha_mu=320.0,
        volume_per_ha_sigma=0.0,
        stem_density_mu=900.0,
        stem_density_sigma=0.0,
        ground_slope_mu=18.0,
        ground_slope_sigma=0.0,
        model=LahrsenModel.DAILY,
        method="monte-carlo",
        samples=10,
    )
    deterministic = estimate_productivity(
        avg_stem_size=0.4,
        volume_per_ha=320.0,
        stem_density=900.0,
        ground_slope=18.0,
    )
    assert pytest.approx(result.expected_m3_per_pmh, rel=1e-6) == deterministic.predicted_m3_per_pmh


def test_labelle2019_clearcut_spruce_polynomial_matches_reference():
    result = estimate_processor_productivity_labelle2019_dbh(
        species="spruce",
        treatment="clear_cut",
        dbh_cm=34.3,
    )
    expected = (-70.18) + 5.301 * 34.3 + (-0.06052) * (34.3**2)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected, rel_tol=1e-9)


def test_labelle2019_invalid_species_pair_raises() -> None:
    with pytest.raises(ValueError):
        estimate_processor_productivity_labelle2019_dbh(
            species="pine",  # type: ignore[arg-type]
            treatment="clear_cut",
            dbh_cm=30.0,
        )


def test_labelle2019_volume_clearcut_spruce() -> None:
    volume = 1.8
    result = estimate_processor_productivity_labelle2019_volume(
        species="spruce",
        treatment="clear_cut",
        volume_m3=volume,
    )
    expected = 2.938 + 54.87 * volume - 16.56 * (volume**2)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected, rel_tol=1e-9)


def test_labelle2019_volume_invalid_combo() -> None:
    with pytest.raises(ValueError):
        estimate_processor_productivity_labelle2019_volume(
            species="spruce",
            treatment="seed_tree",  # type: ignore[arg-type]
            volume_m3=1.2,
        )


def test_labelle2016_treeform_acceptible() -> None:
    result = estimate_processor_productivity_labelle2016(
        tree_form="acceptable",
        dbh_cm=35.0,
    )
    expected = 1.0273 * (35.0 ** 0.8319)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected, rel_tol=1e-9)


def test_labelle2016_bad_treeform_raises() -> None:
    with pytest.raises(ValueError):
        estimate_processor_productivity_labelle2016(
            tree_form="crooked",  # type: ignore[arg-type]
            dbh_cm=30.0,
        )


def test_labelle2017_poly1_matches_formula() -> None:
    dbh = 32.0
    result = estimate_processor_productivity_labelle2017(
        variant="poly1",
        dbh_cm=dbh,
    )
    expected = 27.67 - 5.1784 * dbh + 0.3017 * (dbh**2) - 0.0039 * (dbh**3)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected, rel_tol=1e-9)


def test_labelle2017_power_variant() -> None:
    result = estimate_processor_productivity_labelle2017(
        variant="power2",
        dbh_cm=28.0,
    )
    expected = 0.005 * (28.0 ** 2.629)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected, rel_tol=1e-9)


def test_labelle2018_rw_poly() -> None:
    result = estimate_processor_productivity_labelle2018(
        variant="rw_poly1",
        dbh_cm=33.0,
    )
    expected = -15.15 + 2.53 * 33.0 - 0.02 * (33.0**2)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected, rel_tol=1e-9)


def test_automatic_bucking_multiplier_scales_delay_free_output() -> None:
    adjustment = get_labelle_huss_automatic_bucking_adjustment()
    baseline = estimate_processor_productivity_labelle2016(
        tree_form="acceptable",
        dbh_cm=32.0,
    )
    boosted = estimate_processor_productivity_labelle2016(
        tree_form="acceptable",
        dbh_cm=32.0,
        automatic_bucking_multiplier=adjustment.multiplier,
    )
    ratio = boosted.delay_free_productivity_m3_per_pmh / baseline.delay_free_productivity_m3_per_pmh
    assert math.isclose(ratio, adjustment.multiplier, rel_tol=1e-9)


def test_visser2015_exact_piece_size_values() -> None:
    result = estimate_processor_productivity_visser2015(
        piece_size_m3=2.0,
        log_sort_count=15,
    )
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, 82.0)
    assert math.isclose(result.baseline_productivity_m3_per_pmh, 91.0)
    assert result.relative_difference_percent == pytest.approx(-9.8901098901)


def test_visser2015_interpolates_between_piece_sizes() -> None:
    result = estimate_processor_productivity_visser2015(
        piece_size_m3=1.25,
        log_sort_count=9,
        delay_multiplier=0.8,
    )
    # Linear interpolation between 1.0 m3 (54 m3/PMH) and 1.5 m3 (73 m3/PMH)
    expected_delay_free = 54.0 + (0.25 / 0.5) * (73.0 - 54.0)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected_delay_free)
    assert math.isclose(result.productivity_m3_per_pmh, expected_delay_free * 0.8)


def test_visser2015_invalid_piece_size_raises() -> None:
    with pytest.raises(ValueError):
        estimate_processor_productivity_visser2015(piece_size_m3=0.5, log_sort_count=9)
