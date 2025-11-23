from __future__ import annotations

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    estimate_processor_productivity_adv5n6,
    estimate_processor_productivity_berry2019,
    estimate_processor_productivity_labelle2016,
    estimate_processor_productivity_labelle2017,
    estimate_processor_productivity_labelle2018,
    estimate_processor_productivity_labelle2019_dbh,
    estimate_processor_productivity_labelle2019_volume,
    estimate_processor_productivity_nakagawa2010,
    estimate_processor_productivity_tn103,
    estimate_processor_productivity_tn166,
    estimate_processor_productivity_tr106,
    estimate_processor_productivity_visser2015,
    get_labelle_huss_automatic_bucking_adjustment,
    get_processor_carrier_profile,
)
from tests.cli import CliRunner

runner = CliRunner()


def test_cli_processor_berry2019_basic() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.5",
            "--processor-tree-form",
            "0",
        ],
    )
    assert result.exit_code == 0
    profile = get_processor_carrier_profile("purpose_built")
    expected = estimate_processor_productivity_berry2019(
        piece_size_m3=1.5,
        delay_multiplier=profile.default_delay_multiplier or 0.91,
        carrier_profile=profile,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_processor_automatic_bucking_flag() -> None:
    adjustment = get_labelle_huss_automatic_bucking_adjustment()
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.5",
            "--processor-automatic-bucking",
        ],
    )
    assert result.exit_code == 0
    profile = get_processor_carrier_profile("purpose_built")
    expected = estimate_processor_productivity_berry2019(
        piece_size_m3=1.5,
        automatic_bucking_multiplier=adjustment.multiplier,
        delay_multiplier=profile.default_delay_multiplier or 0.91,
        carrier_profile=profile,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout
    assert "Labelle & Huß (2018" in result.stdout


def test_cli_berry_log_grades_command() -> None:
    result = runner.invoke(dataset_app, ["berry-log-grades"])
    assert result.exit_code == 0, result.stdout
    assert "Berry (2019) Log-Grade" in result.stdout
    assert "Z40" in result.stdout


def test_cli_unbc_hoe_chucking_command() -> None:
    result = runner.invoke(dataset_app, ["unbc-hoe-chucking"])
    assert result.exit_code == 0, result.stdout
    assert "UNBC Hoe-Chucking" in result.stdout
    assert "group" in result.stdout.lower()
    assert "clearcut" in result.stdout.lower()


def test_cli_processor_tree_form_penalty() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.5",
            "--processor-tree-form",
            "2",
            "--processor-crew-multiplier",
            "0.75",
            "--processor-delay-multiplier",
            "0.8",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_berry2019(
        piece_size_m3=1.5,
        tree_form_category=2,
        crew_multiplier=0.75,
        delay_multiplier=0.8,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_processor_show_grade_stats() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.2",
            "--processor-show-grade-stats",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Berry (2019) Log-Grade" in result.stdout
    assert "Z40" in result.stdout


def test_cli_processor_labelle2019_dbh() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "labelle2019_dbh",
            "--processor-dbh-cm",
            "34.0",
            "--processor-species",
            "spruce",
            "--processor-treatment",
            "clear_cut",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_labelle2019_dbh(
        species="spruce",
        treatment="clear_cut",
        dbh_cm=34.0,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_processor_labelle2019_volume() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "labelle2019_volume",
            "--processor-volume-m3",
            "1.9",
            "--processor-species",
            "beech",
            "--processor-treatment",
            "selective_cut",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_labelle2019_volume(
        species="beech",
        treatment="selective_cut",
        volume_m3=1.9,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_processor_harvest_system_defaults_cable_running() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--harvest-system-id",
            "cable_running",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "adv7n3" in result.stdout
    assert "Hyundai 210LC" in result.stdout
    assert "Applied productivity defaults from harvest system" in result.stdout
    assert "'cable_running'" in result.stdout


def test_cli_processor_harvest_system_defaults_adv5n28_clearcut() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--harvest-system-id",
            "cable_running_adv5n28_clearcut",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "adv7n3" in result.stdout
    assert "John Deere 892" in result.stdout
    assert "Applied productivity defaults from harvest system" in result.stdout
    assert "'cable_running_adv5n28_clearcut'" in result.stdout


def test_cli_processor_spinelli2010_process() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "spinelli2010",
            "--processor-piece-size-m3",
            "0.45",
            "--processor-machine-power-kw",
            "125",
            "--processor-slope-percent",
            "14",
            "--processor-spinelli-operation",
            "process",
            "--processor-spinelli-carrier",
            "excavator",
            "--processor-spinelli-head",
            "roller",
            "--processor-spinelli-species",
            "other_hardwood",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Spinelli (2010)" in result.stdout


def test_cli_processor_bertone2025() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "bertone2025",
            "--processor-piece-size-m3",
            "1.0",
            "--processor-dbh-cm",
            "35",
            "--processor-tree-height-m",
            "21",
            "--processor-logs-per-tree",
            "3",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "bertone2025" in result.stdout


def test_cli_processor_borz2023() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "borz2023",
            "--processor-piece-size-m3",
            "1.0",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "borz2023" in result.stdout


def test_cli_processor_labelle2016_treeform() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "labelle2016",
            "--processor-dbh-cm",
            "32.0",
            "--processor-labelle2016-form",
            "unacceptable",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_labelle2016(
        tree_form="unacceptable",
        dbh_cm=32.0,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_processor_labelle2017_variant() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "labelle2017",
            "--processor-dbh-cm",
            "31.0",
            "--processor-labelle2017-variant",
            "power1",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_labelle2017(
        variant="power1",
        dbh_cm=31.0,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_processor_labelle2018_variant() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "labelle2018",
            "--processor-dbh-cm",
            "35.0",
            "--processor-labelle2018-variant",
            "ct_poly1",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_labelle2018(
        variant="ct_poly1",
        dbh_cm=35.0,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_processor_visser2015() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "visser2015",
            "--processor-piece-size-m3",
            "2.0",
            "--processor-log-sorts",
            "15",
            "--processor-delay-multiplier",
            "0.8",
        ],
    )
    assert result.exit_code == 0, result.stdout
    expected = estimate_processor_productivity_visser2015(
        piece_size_m3=2.0,
        log_sort_count=15,
        delay_multiplier=0.8,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout
    assert "Visser & Tolan (2015)" in result.stdout


def test_cli_processor_nakagawa2010_with_dbh() -> None:
    delay_multiplier = 0.82
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "nakagawa2010",
            "--processor-dbh-cm",
            "20.0",
            "--processor-delay-multiplier",
            str(delay_multiplier),
        ],
    )
    assert result.exit_code == 0, result.stdout
    expected = estimate_processor_productivity_nakagawa2010(
        dbh_cm=20.0,
        delay_multiplier=delay_multiplier,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout
    assert "nakagawa2010" in result.stdout


def test_cli_processor_nakagawa2010_requires_inputs() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "nakagawa2010",
        ],
    )
    assert result.exit_code != 0
    assert "processor-piece-size-m3" in result.stdout or "processor-dbh-cm" in result.stdout


def test_cli_processor_visser2015_requires_log_sorts() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "visser2015",
            "--processor-piece-size-m3",
            "2.0",
        ],
    )
    assert result.exit_code != 0
    assert "processor-log-sorts" in result.stdout


def test_cli_processor_excavator_carrier() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.8",
            "--processor-carrier",
            "excavator",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Carrier" in result.stdout
    assert "excavator" in result.stdout.lower()


def test_cli_processor_berry2019_skid_area_auto_multiplier() -> None:
    skid_area = 2600.0
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.5",
            "--processor-skid-area-m2",
            str(skid_area),
        ],
    )
    assert result.exit_code == 0
    profile = get_processor_carrier_profile("purpose_built")
    base_result = estimate_processor_productivity_berry2019(
        piece_size_m3=1.5,
        delay_multiplier=1.0,
        carrier_profile=profile,
    )
    base_prod = base_result.delay_free_productivity_m3_per_pmh
    predicted_delay = -0.015 * skid_area + 53.0
    base_multiplier = profile.default_delay_multiplier or 0.91
    expected_multiplier = max(min(base_multiplier * (10.9 / predicted_delay), 1.0), 0.01)
    expected_productivity = base_prod * expected_multiplier
    assert f"{expected_productivity:.2f}" in result.stdout
    assert "Berry skid-size model predicts" in result.stdout


def test_cli_processor_adv5n6_loader_forwarded_cold() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "adv5n6",
            "--processor-stem-source",
            "loader_forwarded",
            "--processor-processing-mode",
            "cold",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_adv5n6(
        stem_source="loader_forwarded",
        processing_mode="cold",
    )
    assert f"{expected.productivity_m3_per_smh:.1f}" in result.stdout


def test_cli_processor_adv5n6_rejects_loader_hot() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "adv5n6",
            "--processor-stem-source",
            "loader_forwarded",
            "--processor-processing-mode",
            "hot",
        ],
    )
    assert result.exit_code != 0
    assert "ADV5N6 only reports loader-forwarded data for cold processing" in result.stdout


def test_cli_processor_tn103_area_a() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "tn103",
            "--processor-tn103-scenario",
            "area_a_feller_bunched",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_tn103(scenario="area_a_feller_bunched")
    assert f"{expected.productivity_m3_per_smh:.1f}" in result.stdout


def test_cli_processor_tr106_kp40() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "tr106",
            "--processor-tr106-scenario",
            "kp40_caterpillar_el180",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_tr106(scenario="kp40_caterpillar_el180")
    assert f"{expected.productivity_m3_per_pmh:.1f}" in result.stdout


def test_cli_processor_tn166_right_of_way() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "tn166",
            "--processor-tn166-scenario",
            "right_of_way",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_tn166(scenario="right_of_way")
    assert f"{expected.productivity_m3_per_smh:.1f}" in result.stdout


def test_cli_processor_adv7n3_john_deere() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-model",
            "adv7n3",
            "--processor-adv7n3-machine",
            "john_deere_892",
        ],
    )
    assert result.exit_code == 0
    assert "John Deere 892" in result.stdout
    assert "Processor + Loader (2024 CAD" in result.stdout


def test_cli_processor_berry2019_skid_area_respects_manual_delay() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.5",
            "--processor-skid-area-m2",
            "2600",
            "--processor-delay-multiplier",
            "0.8",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_berry2019(
        piece_size_m3=1.5,
        delay_multiplier=0.8,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout
    assert "Delay multiplier left" in result.stdout
    assert "unchanged because --processor-delay-multiplier was supplied" in result.stdout
