from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app

runner = CliRunner()


def test_cli_helicopter_longline_default_kmax() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "helicopter_longline",
            "--helicopter-model",
            "kmax",
            "--helicopter-flight-distance-m",
            "400",
        ],
    )
    assert result.exit_code == 0
    assert "Model" in result.stdout
    assert "kmax" in result.stdout


def test_cli_helicopter_longline_harvest_system_defaults() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "helicopter_longline",
            "--harvest-system-id",
            "helicopter",
        ],
    )
    assert result.exit_code == 0
    assert "bell214b" in result.stdout.lower()
    assert "Applied helicopter defaults" in result.stdout


def test_cli_helicopter_preset_defaults_and_costs() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "helicopter_longline",
            "--helicopter-model",
            "s64e_aircrane",
            "--helicopter-preset",
            "s64e_grapple_retention_adv5n13",
            "--show-costs",
        ],
    )
    assert result.exit_code == 0
    assert "Preset 's64e_grapple_retention_adv5n13'" in result.stdout
    assert "helicopter_s64e_aircrane" in result.stdout


def test_cli_helicopter_dataset_listing() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "helicopter-fpinnovations",
            "--model",
            "s64e_aircrane",
        ],
    )
    assert result.exit_code == 0
    assert "helicopter presets" in result.stdout.lower()
