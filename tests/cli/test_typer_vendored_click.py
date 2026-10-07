"""Regression tests for Typer >= 0.26, which vendors Click as ``typer._click`` (#103).

These live under ``tests/cli/`` so they run in the default (ungated) pytest invocation.
"""

from __future__ import annotations

import typer
from typer.testing import CliRunner

from fhops.cli.dataset import _parameter_supplied, dataset_app
from fhops.cli.main import KpiMode, app
from fhops.productivity import estimate_cable_yarder_productivity_lee2018_uphill

runner = CliRunner()


def _supplied_flags(args: list[str]) -> dict[str, bool]:
    probe = typer.Typer()
    seen: dict[str, bool] = {}

    @probe.command()
    def main(
        ctx: typer.Context,
        optional: str | None = typer.Option(None, "--optional"),
        valued: int = typer.Option(3, "--valued"),
    ) -> None:
        seen["optional"] = _parameter_supplied(ctx, "optional")
        seen["valued"] = _parameter_supplied(ctx, "valued")

    result = runner.invoke(probe, args)
    assert result.exit_code == 0, result.output
    return seen


def test_parameter_supplied_ignores_defaults() -> None:
    assert _supplied_flags([]) == {"optional": False, "valued": False}


def test_parameter_supplied_detects_command_line_values() -> None:
    assert _supplied_flags(["--optional", "x", "--valued", "3"]) == {
        "optional": True,
        "valued": True,
    }


def test_skyline_default_invocation_is_not_rejected() -> None:
    result = runner.invoke(
        dataset_app,
        ["estimate-skyline-productivity", "--model", "lee-uphill", "--slope-distance-m", "400"],
    )
    assert result.exit_code == 0, result.output
    assert "--fncy12-variant is only valid" not in result.output
    expected = estimate_cable_yarder_productivity_lee2018_uphill(
        yarding_distance_m=400.0, payload_m3=0.57
    )
    assert f"{expected:.2f}" in result.output


def test_grapple_yarder_harvest_system_defaults_apply() -> None:
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
    assert result.exit_code == 0, result.output
    assert "Applied grapple-yarder defaults from harvest system 'cable_running'" in result.output


def test_kpi_mode_rejects_unknown_value_with_usage_error() -> None:
    result = runner.invoke(
        app,
        [
            "evaluate",
            "examples/tiny7/scenario.yaml",
            "--assignments",
            "missing.csv",
            "--kpi-mode",
            "bogus",
        ],
    )
    assert result.exit_code == 2
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "'bogus' is not one of 'basic', 'extended'" in result.output


def test_kpi_mode_values_are_strings() -> None:
    assert KpiMode("basic") == "basic"
    assert KpiMode.EXTENDED.lower() == "extended"
