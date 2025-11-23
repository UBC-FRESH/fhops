from __future__ import annotations

from fhops.cli.dataset import dataset_app
from tests.cli import CliRunner

runner = CliRunner()


def test_cli_tn98_handfalling_douglas_fir() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "tn98-handfalling",
            "--species",
            "douglas_fir",
            "--dbh-cm",
            "52.5",
        ],
    )
    assert result.exit_code == 0
    assert "1.44" in result.stdout  # regression output for 52.5 cm Douglas-fir
    assert "Cost per tree" in result.stdout


def test_cli_tn98_handfalling_show_table() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "tn98-handfalling",
            "--show-table",
        ],
    )
    assert result.exit_code == 0
    assert "TN98 per-diameter observations" in result.stdout or (
        "No per-diameter table" in result.stdout
    )
