from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app

runner = CliRunner()


def test_cli_tn82_ft180_command() -> None:
    result = runner.invoke(dataset_app, ["tn82-ft180"])
    assert result.exit_code == 0
    assert "FMC FT-180" in result.stdout
    assert "John Deere 550" in result.stdout
