from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    Han2018SkidderMethod,
    KelloggLoadType,
    estimate_grapple_skidder_productivity_han2018,
    estimate_harvester_productivity_adv5n30,
    estimate_harvester_productivity_adv6n10,
    estimate_harvester_productivity_tn292,
    estimate_forwarder_productivity_kellogg_bettinger,
    estimate_forwarder_productivity_small_forwarder_thinning,
)
from fhops.productivity.harvester_ctl import ADV6N10HarvesterInputs, TN292HarvesterInputs
from fhops.productivity.forwarder_bc import (
    ForwarderBCModel,
    estimate_forwarder_productivity_bc,
)

runner = CliRunner()


def test_cli_forwarder_productivity_ghaffariyan_small() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-forwarder-productivity",
            "--model",
            "ghaffariyan-small",
            "--extraction-distance",
            "100",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_small_forwarder_thinning(100.0)
    assert f"{expected:.2f}" in result.stdout


def test_cli_forwarder_productivity_ghaffariyan_small_slope_class() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-forwarder-productivity",
            "--model",
            "ghaffariyan-small",
            "--extraction-distance",
            "200",
            "--slope-class",
            "10-20",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_small_forwarder_thinning(200.0, slope_factor=0.75)
    assert f"{expected:.2f}" in result.stdout


def test_cli_forwarder_productivity_kellogg_mixed() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-forwarder-productivity",
            "--model",
            "kellogg-mixed",
            "--volume-per-load",
            "9.3",
            "--distance-out",
            "274",
            "--travel-in-unit",
            "76",
            "--distance-in",
            "259",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_kellogg_bettinger(
        load_type=KelloggLoadType.MIXED,
        volume_per_load_m3=9.3,
        distance_out_m=274.0,
        travel_in_unit_m=76.0,
        distance_in_m=259.0,
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_forwarder_productivity_adv6n10() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-forwarder-productivity",
            "--model",
            "adv6n10-shortwood",
            "--payload-per-trip",
            "10",
            "--mean-log-length",
            "5",
            "--travel-speed",
            "40",
            "--trail-length",
            "300",
            "--products-per-trail",
            "2",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.ADV6N10_SHORTWOOD,
        payload_m3=10.0,
        mean_log_length_m=5.0,
        travel_speed_m_per_min=40.0,
        trail_length_m=300.0,
        products_per_trail=2.0,
    ).predicted_m3_per_pmh
    assert f"{expected:.2f}" in result.stdout


def test_cli_forwarder_productivity_eriksson_final_felling() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-forwarder-productivity",
            "--model",
            "eriksson-final-felling",
            "--mean-extraction-distance",
            "300",
            "--mean-stem-size",
            "0.25",
            "--load-capacity",
            "14",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.ERIKSSON_FINAL_FELLING,
        mean_extraction_distance_m=300.0,
        mean_stem_size_m3=0.25,
        load_capacity_m3=14.0,
    ).predicted_m3_per_pmh
    assert f"{expected:.2f}" in result.stdout


def test_cli_forwarder_productivity_brushwood() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-forwarder-productivity",
            "--model",
            "laitila-vaatainen-brushwood",
            "--harvested-trees-per-ha",
            "1500",
            "--avg-tree-volume-dm3",
            "45",
            "--forwarding-distance",
            "200",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.LAITILA_VAATAINEN_BRUSHWOOD,
        harvested_trees_per_ha=1500,
        average_tree_volume_dm3=45.0,
        forwarding_distance_m=200.0,
    ).predicted_m3_per_pmh
    assert f"{expected:.2f}" in result.stdout


def test_cli_estimate_productivity_forwarder_branch() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "forwarder",
            "--forwarder-model",
            "kellogg-mixed",
            "--volume-per-load",
            "9.3",
            "--distance-out",
            "274",
            "--travel-in-unit",
            "76",
            "--distance-in",
            "259",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_kellogg_bettinger(
        load_type=KelloggLoadType.MIXED,
        volume_per_load_m3=9.3,
        distance_out_m=274.0,
        travel_in_unit_m=76.0,
        distance_in_m=259.0,
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_estimate_productivity_forwarder_adv6n10_branch() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "forwarder",
            "--forwarder-model",
            "adv6n10-shortwood",
            "--payload-per-trip",
            "10",
            "--mean-log-length",
            "5",
            "--travel-speed",
            "40",
            "--trail-length",
            "300",
            "--products-per-trail",
            "2",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.ADV6N10_SHORTWOOD,
        payload_m3=10.0,
        mean_log_length_m=5.0,
        travel_speed_m_per_min=40.0,
        trail_length_m=300.0,
        products_per_trail=2.0,
    ).predicted_m3_per_pmh
    assert f"{expected:.2f}" in result.stdout


def test_cli_estimate_productivity_forwarder_eriksson_branch() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "forwarder",
            "--forwarder-model",
            "eriksson-thinning",
            "--mean-extraction-distance",
            "300",
            "--mean-stem-size",
            "0.15",
            "--load-capacity",
            "12",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.ERIKSSON_THINNING,
        mean_extraction_distance_m=300.0,
        mean_stem_size_m3=0.15,
        load_capacity_m3=12.0,
    ).predicted_m3_per_pmh
    assert f"{expected:.2f}" in result.stdout


def test_cli_estimate_productivity_forwarder_brushwood_branch() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "forwarder",
            "--forwarder-model",
            "laitila-vaatainen-brushwood",
            "--harvested-trees-per-ha",
            "1500",
            "--avg-tree-volume-dm3",
            "45",
            "--forwarding-distance",
            "200",
            "--harwarder-payload",
            "7.1",
            "--grapple-load-unloading",
            "0.29",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.LAITILA_VAATAINEN_BRUSHWOOD,
        harvested_trees_per_ha=1500.0,
        average_tree_volume_dm3=45.0,
        forwarding_distance_m=200.0,
        harwarder_payload_m3=7.1,
        grapple_load_unloading_m3=0.29,
    ).predicted_m3_per_pmh
    assert f"{expected:.2f}" in result.stdout


def test_cli_estimate_productivity_grapple_skidder_branch() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_skidder",
            "--grapple-skidder-model",
            "lop_and_scatter",
            "--skidder-pieces-per-cycle",
            "18",
            "--skidder-piece-volume",
            "0.22",
            "--skidder-empty-distance",
            "140",
            "--skidder-loaded-distance",
            "120",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_grapple_skidder_productivity_han2018(
        method=Han2018SkidderMethod.LOP_AND_SCATTER,
        pieces_per_cycle=18.0,
        piece_volume_m3=0.22,
        empty_distance_m=140.0,
        loaded_distance_m=120.0,
    ).predicted_m3_per_pmh
    assert f"{expected:.2f}" in result.stdout


def test_cli_estimate_productivity_ctl_harvester_adv6n10() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "ctl_harvester",
            "--ctl-harvester-model",
            "adv6n10",
            "--ctl-stem-volume",
            "0.12",
            "--ctl-products-count",
            "3",
            "--ctl-stems-per-cycle",
            "1.4",
            "--ctl-mean-log-length",
            "4.8",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_harvester_productivity_adv6n10(
        ADV6N10HarvesterInputs(
            stem_volume_m3=0.12,
            products_count=3.0,
            stems_per_cycle=1.4,
            mean_log_length_m=4.8,
        )
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_estimate_productivity_ctl_harvester_adv5n30() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "ctl_harvester",
            "--ctl-harvester-model",
            "adv5n30",
            "--ctl-removal-fraction",
            "0.5",
            "--ctl-brushed",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_harvester_productivity_adv5n30(removal_fraction=0.5, brushed=True)
    assert f"{expected:.2f}" in result.stdout


def test_cli_estimate_productivity_ctl_harvester_tn292() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "ctl_harvester",
            "--ctl-harvester-model",
            "tn292",
            "--ctl-stem-volume",
            "0.12",
            "--ctl-density",
            "1500",
            "--ctl-density-basis",
            "post",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_harvester_productivity_tn292(
        TN292HarvesterInputs(stem_volume_m3=0.12, stand_density_per_ha=1500, density_basis="post")
    )
    assert f"{expected:.2f}" in result.stdout
