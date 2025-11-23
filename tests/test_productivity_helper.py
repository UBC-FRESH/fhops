import math

import numpy as np
import pytest

from fhops.core import FHOPSValueError
from fhops.productivity import (
    LahrsenModel,
    estimate_processor_productivity_adv7n3,
    estimate_processor_productivity_berry2019,
    estimate_processor_productivity_bertone2025,
    estimate_processor_productivity_borz2023,
    estimate_processor_productivity_hypro775,
    estimate_processor_productivity_labelle2016,
    estimate_processor_productivity_labelle2017,
    estimate_processor_productivity_labelle2018,
    estimate_processor_productivity_labelle2019_dbh,
    estimate_processor_productivity_labelle2019_volume,
    estimate_processor_productivity_nakagawa2010,
    estimate_processor_productivity_spinelli2010,
    estimate_processor_productivity_visser2015,
    estimate_productivity,
    estimate_productivity_distribution,
    get_labelle_huss_automatic_bucking_adjustment,
    get_processor_carrier_profile,
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
    expected = 1.0273 * (35.0**0.8319)
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
    expected = 0.005 * (28.0**2.629)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected, rel_tol=1e-9)


def test_labelle2018_rw_poly() -> None:
    result = estimate_processor_productivity_labelle2018(
        variant="rw_poly1",
        dbh_cm=33.0,
    )
    expected = -15.15 + 2.53 * 33.0 - 0.02 * (33.0**2)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, expected, rel_tol=1e-9)


def test_hypro775_delay_multiplier_scales_output() -> None:
    result = estimate_processor_productivity_hypro775(delay_multiplier=0.5)
    assert math.isclose(
        result.delay_free_productivity_m3_per_pmh * 0.5, result.productivity_m3_per_pmh
    )
    assert math.isclose(result.mean_cycle_time_seconds, 45.0)


def test_hypro775_invalid_multiplier_raises() -> None:
    with pytest.raises(ValueError):
        estimate_processor_productivity_hypro775(delay_multiplier=1.2)


def test_adv7n3_processor_summary_matches_report() -> None:
    result = estimate_processor_productivity_adv7n3(machine="john_deere_892")
    assert math.isclose(result.shift_productivity_m3_per_pmh, 40.1, rel_tol=1e-6)
    assert result.machine_label.lower().startswith("john deere 892")
    assert result.system_cost_cad_per_m3_base_year is not None
    assert math.isclose(result.system_cost_cad_per_m3_base_year, 8.21, rel_tol=1e-4)


def test_spinelli2010_harvest_matches_formulas() -> None:
    params = dict(
        operation="harvest",
        tree_volume_m3=0.55,
        slope_percent=18.0,
        machine_power_kw=150.0,
        carrier_type="purpose_built",
        head_type="roller",
        species_group="conifer",
        stand_type="forest",
        removals_per_ha=380.0,
        residuals_per_ha=250.0,
    )
    result = estimate_processor_productivity_spinelli2010(**params)
    power_term = math.sqrt(150.0)
    move = 7.5 + (12_412 + 771 * 18.0) / (380.0 * power_term) + 0.204 * 250.0 / power_term
    brush = max(0.0, -1.8 + 9.2)
    fell = 3.8 + 156.5 * 0.55 / power_term + 1.18 * 18.0
    process = 22.7 + 1.433 * 0.55 * 18.0 + (1_115.0) * 0.55 / power_term
    expected_minutes = 0.01 * (move + brush + fell + process)
    expected_delay_free = 0.55 * 60.0 / expected_minutes
    assert math.isclose(
        result.delay_free_productivity_m3_per_pmh, expected_delay_free, rel_tol=1e-9
    )
    expected_multiplier = 1.0 / ((1.0 + 0.147) * (1.0 + 0.5))
    assert math.isclose(
        result.productivity_m3_per_pmh,
        expected_delay_free * expected_multiplier,
        rel_tol=1e-9,
    )


def test_spinelli2010_process_cycle_components() -> None:
    result = estimate_processor_productivity_spinelli2010(
        operation="process",
        tree_volume_m3=0.4,
        slope_percent=12.0,
        machine_power_kw=135.0,
        carrier_type="excavator",
        head_type="stroke",
        species_group="other_hardwood",
        stand_type="plantation",
    )
    component_sum = sum(minutes for _, minutes in result.cycle_components_minutes)
    assert math.isclose(component_sum, result.delay_free_minutes_per_tree)
    assert result.removals_per_ha is None
    assert result.residuals_per_ha is None
    assert result.productivity_m3_per_pmh < result.delay_free_productivity_m3_per_pmh
    assert result.productivity_m3_per_pmh < result.delay_free_productivity_m3_per_pmh


def test_bertone2025_matches_reference_cycle() -> None:
    dbh = 34.7
    height = 20.7
    logs = 3.2
    volume = 1.0
    result = estimate_processor_productivity_bertone2025(
        dbh_cm=dbh,
        height_m=height,
        logs_per_tree=logs,
        tree_volume_m3=volume,
    )
    expected_cycle = -8.1893 + 2.3810 * dbh + 1.8789 * height + 5.6562 * logs
    assert math.isclose(result.delay_free_cycle_seconds, expected_cycle, rel_tol=1e-9)
    delay_free_prod = volume * (3600.0 / expected_cycle)
    assert math.isclose(result.delay_free_productivity_m3_per_pmh, delay_free_prod, rel_tol=1e-9)
    assert result.productivity_m3_per_smh == pytest.approx(14.8, rel=1e-2)


def test_borz2023_returns_expected_means() -> None:
    result = estimate_processor_productivity_borz2023(tree_volume_m3=1.0)
    assert math.isclose(result.productivity_m3_per_pmh, 21.41, rel_tol=1e-9)
    assert math.isclose(result.fuel_l_per_m3, 0.78, rel_tol=1e-9)
    assert result.cost_per_m3 == pytest.approx(10.5, rel=1e-2)


def test_nakagawa2010_dbh_and_volume_paths() -> None:
    dbh_cm = 19.6
    piece_volume = 0.25
    result_dbh = estimate_processor_productivity_nakagawa2010(
        dbh_cm=dbh_cm,
        delay_multiplier=0.85,
    )
    expected_dbh = 0.363 * (dbh_cm**1.116)
    assert math.isclose(result_dbh.delay_free_productivity_m3_per_pmh, expected_dbh, rel_tol=1e-9)
    assert math.isclose(result_dbh.productivity_m3_per_pmh, expected_dbh * 0.85, rel_tol=1e-9)
    result_piece = estimate_processor_productivity_nakagawa2010(
        piece_volume_m3=piece_volume,
    )
    expected_piece = 20.46 * (piece_volume**0.482)
    assert math.isclose(
        result_piece.delay_free_productivity_m3_per_pmh, expected_piece, rel_tol=1e-9
    )
    assert math.isclose(result_piece.delay_multiplier, 1.0, rel_tol=1e-9)


def test_nakagawa2010_missing_inputs_raise() -> None:
    with pytest.raises(ValueError):
        estimate_processor_productivity_nakagawa2010()  # type: ignore[call-arg]


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


def test_berry2019_excavator_carrier_adjustment() -> None:
    profile_excavator = get_processor_carrier_profile("excavator")
    profile_purpose = get_processor_carrier_profile("purpose_built")
    base = estimate_processor_productivity_berry2019(
        piece_size_m3=1.5,
        carrier_profile=profile_purpose,
    )
    excavator = estimate_processor_productivity_berry2019(
        piece_size_m3=1.5,
        carrier_profile=profile_excavator,
    )
    ratio = excavator.delay_free_productivity_m3_per_pmh / base.delay_free_productivity_m3_per_pmh
    assert math.isclose(
        ratio,
        profile_excavator.productivity_ratio / profile_purpose.productivity_ratio,
        rel_tol=1e-9,
    )
