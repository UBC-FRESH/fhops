from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    KelloggLoadType,
    estimate_forwarder_productivity_kellogg_bettinger,
    estimate_forwarder_productivity_small_forwarder_thinning,
)

runner = CliRunner()


def test_cli_forwarder_productivity_ghaffariyan_small() -> None:
    result = runner.invoke(
        dataset_app,
        ["estimate-forwarder-productivity", "--model", "ghaffariyan-small", "--extraction-distance", "100"],
    )
    assert result.exit_code == 0
    expected = estimate_forwarder_productivity_small_forwarder_thinning(100.0)
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
