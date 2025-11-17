from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    KelloggLoadType,
    estimate_forwarder_productivity_kellogg_bettinger,
    estimate_forwarder_productivity_small_forwarder_thinning,
)
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
