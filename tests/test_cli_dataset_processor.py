from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    estimate_processor_productivity_berry2019,
    estimate_processor_productivity_labelle2016,
    estimate_processor_productivity_labelle2017,
    estimate_processor_productivity_labelle2018,
    estimate_processor_productivity_labelle2019_dbh,
    estimate_processor_productivity_labelle2019_volume,
    estimate_processor_productivity_adv5n6,
    estimate_processor_productivity_tn166,
)

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
    expected = estimate_processor_productivity_berry2019(piece_size_m3=1.5)
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


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
    base_prod = 34.7 * 1.5 + 11.3
    predicted_delay = -0.015 * skid_area + 53.0
    expected_multiplier = max(min(0.91 * (10.9 / predicted_delay), 1.0), 0.01)
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
