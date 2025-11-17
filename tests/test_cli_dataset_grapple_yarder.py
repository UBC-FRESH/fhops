from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import estimate_grapple_yarder_productivity_sr54

runner = CliRunner()


def test_cli_grapple_yarder_sr54() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "sr54",
            "--grapple-turn-volume-m3",
            "2.4",
            "--grapple-yard-distance-m",
            "180",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_grapple_yarder_productivity_sr54(turn_volume_m3=2.4, yarding_distance_m=180.0)
    assert f"{expected:.2f}" in result.stdout


def test_cli_grapple_yarder_harvest_system_defaults() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--harvest-system-id",
            "cable_running",
        ],
    )
    assert result.exit_code == 0
    assert "Applied grapple-yarder defaults" in result.stdout
