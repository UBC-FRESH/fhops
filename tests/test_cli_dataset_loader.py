from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import estimate_loader_forwarder_productivity_tn261

runner = CliRunner()


def test_cli_loader_bunched() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "loader",
            "--loader-piece-size-m3",
            "1.2",
            "--loader-distance-m",
            "100",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_loader_forwarder_productivity_tn261(
        piece_size_m3=1.2,
        external_distance_m=100.0,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_loader_hand_felled_with_slope() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "loader",
            "--loader-piece-size-m3",
            "0.9",
            "--loader-distance-m",
            "140",
            "--loader-slope-percent",
            "10",
            "--loader-hand-felled",
            "--loader-delay-multiplier",
            "0.85",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_loader_forwarder_productivity_tn261(
        piece_size_m3=0.9,
        external_distance_m=140.0,
        slope_percent=10.0,
        bunched=False,
        delay_multiplier=0.85,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout
