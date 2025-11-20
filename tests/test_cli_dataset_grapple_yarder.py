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


def test_cli_grapple_yarder_tn147_case() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "tn147",
            "--tn147-case",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert "Case 2" in result.stdout


def test_cli_grapple_yarder_tn147_show_costs_uses_madill_rate() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "tn147",
            "--tn147-case",
            "1",
            "--show-costs",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "grapple_yarder_madill009" in result.stdout


def test_cli_grapple_yarder_tr122_extended() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "tr122-extended",
        ],
    )
    assert result.exit_code == 0
    assert "Extended Rotation" in result.stdout
    assert "Roberts Creek" in result.stdout


def test_cli_grapple_yarder_tn157_case() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "tn157",
            "--tn157-case",
            "4",
        ],
    )
    assert result.exit_code == 0
    assert "Case 4" in result.stdout
    assert "Observed Cost" in result.stdout


def test_cli_grapple_yarder_tn157_show_costs_uses_cypress_rate() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "tn157",
            "--tn157-case",
            "combined",
            "--show-costs",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "grapple_yarder_cypress7280" in result.stdout


def test_cli_grapple_yarder_adv5n28_clearcut() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "adv5n28-clearcut",
        ],
    )
    assert result.exit_code == 0
    assert "ADV5N28" in result.stdout
    assert "2002 CAD" in result.stdout


def test_cli_grapple_yarder_adv5n28_show_costs() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "adv5n28-clearcut",
            "--show-costs",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "grapple_yarder_adv5n28" in result.stdout


def test_cli_grapple_yarder_adv5n28_harvest_system_defaults() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--harvest-system-id",
            "cable_running_adv5n28_clearcut",
        ],
    )
    assert result.exit_code == 0
    assert "ADV5N28" in result.stdout
    assert "Applied grapple-yarder defaults" in result.stdout


def test_cli_grapple_yarder_adv1n35_regression() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "adv1n35",
            "--grapple-turn-volume-m3",
            "1.97",
            "--grapple-yard-distance-m",
            "165",
            "--grapple-lateral-distance-m",
            "11",
            "--grapple-stems-per-cycle",
            "2.83",
            "--grapple-in-cycle-delay-minutes",
            "0.69",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "adv1n35" in result.stdout
    assert "Owren 400" in result.stdout
    assert "Lateral Distance" in result.stdout


def test_cli_grapple_yarder_adv1n40_regression() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--grapple-yarder-model",
            "adv1n40",
            "--grapple-yard-distance-m",
            "120",
            "--grapple-turn-volume-m3",
            "3.0",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Madill 071" in result.stdout
    assert "ADV1N40" in result.stdout or "downhill running" in result.stdout


def test_cli_grapple_yarder_harvest_system_salvage() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "grapple_yarder",
            "--harvest-system-id",
            "cable_salvage_grapple",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Cypress 7280B" in result.stdout
    assert "Applied grapple-yarder defaults" in result.stdout
