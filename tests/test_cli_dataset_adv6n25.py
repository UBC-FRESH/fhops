from __future__ import annotations

from fhops.cli.dataset import dataset_app
from tests.cli import CliRunner

runner = CliRunner()


def test_cli_adv6n25_command() -> None:
    result = runner.invoke(dataset_app, ["adv6n25-helicopters"])
    assert result.exit_code == 0
    assert "Lama" in result.stdout
    assert "K-Max" in result.stdout


def test_cli_adv6n25_show_alternatives() -> None:
    result = runner.invoke(dataset_app, ["adv6n25-helicopters", "--show-alternatives"])
    assert result.exit_code == 0
    assert "Alternative scenarios" in result.stdout
