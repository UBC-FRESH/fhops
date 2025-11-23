from __future__ import annotations

from fhops.cli.dataset import dataset_app
from tests.cli import CliRunner

runner = CliRunner()


def test_cli_tn82_ft180_command() -> None:
    result = runner.invoke(dataset_app, ["tn82-ft180"])
    assert result.exit_code == 0
    assert "FMC FT-180" in result.stdout
    assert "John Deere 550" in result.stdout
