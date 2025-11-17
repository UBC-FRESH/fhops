from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import estimate_processor_productivity_berry2019

runner = CliRunner()


def test_cli_processor_berry2019_basic() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.5",
            "--processor-tree-form",
            "0",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_berry2019(piece_size_m3=1.5)
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_processor_tree_form_penalty() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "roadside_processor",
            "--processor-piece-size-m3",
            "1.5",
            "--processor-tree-form",
            "2",
            "--processor-crew-multiplier",
            "0.75",
            "--processor-delay-multiplier",
            "0.8",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_processor_productivity_berry2019(
        piece_size_m3=1.5,
        tree_form_category=2,
        crew_multiplier=0.75,
        delay_multiplier=0.8,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout
