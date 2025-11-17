from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    HelicopterLonglineModel,
    estimate_helicopter_longline_productivity,
)

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
    expected = estimate_helicopter_longline_productivity(
        model=HelicopterLonglineModel.KMAX,
        flight_distance_m=400.0,
    )
    assert f"{expected.productivity_m3_per_pmh0:.2f}" in result.stdout


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
