from __future__ import annotations

import json

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    estimate_loader_forwarder_productivity_adv5n1,
    estimate_clambunk_productivity_adv2n26,
    estimate_loader_forwarder_productivity_tn261,
)

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


def test_cli_loader_adv2n26_defaults() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "loader",
            "--loader-model",
            "adv2n26",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_clambunk_productivity_adv2n26(
        travel_empty_distance_m=236.0,
        stems_per_cycle=19.7,
    )
    assert f"{expected.productivity_m3_per_smh:.2f}" in result.stdout


def test_cli_loader_adv5n1_slope_class() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "loader",
            "--loader-model",
            "adv5n1",
            "--loader-distance-m",
            "80",
            "--loader-slope-class",
            "11_30",
            "--loader-payload-m3",
            "3.1",
            "--loader-utilisation",
            "0.9",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_loader_forwarder_productivity_adv5n1(
        forwarding_distance_m=80.0,
        slope_class="11_30",
        payload_m3_per_cycle=3.1,
        utilisation=0.9,
    )
    assert f"{expected.productivity_m3_per_smh:.2f}" in result.stdout


def test_cli_loader_telemetry(tmp_path) -> None:
    log_file = tmp_path / "loader.jsonl"
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "loader",
            "--loader-piece-size-m3",
            "1.1",
            "--loader-distance-m",
            "120",
            "--telemetry-log",
            str(log_file),
        ],
    )
    assert result.exit_code == 0
    data = json.loads(log_file.read_text().strip().splitlines()[0])
    assert data["loader_model"] == "tn261"
    assert data["inputs"]["piece_size_m3"] == 1.1


def test_cli_loader_harvest_system_defaults_tn261() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "loader",
            "--harvest-system-id",
            "ground_fb_skid",
        ],
    )
    assert result.exit_code == 0, result.stdout
    expected = estimate_loader_forwarder_productivity_tn261(
        piece_size_m3=1.05,
        external_distance_m=115.0,
        slope_percent=8.0,
        bunched=True,
        delay_multiplier=0.95,
    )
    assert f"{expected.productivity_m3_per_pmh:.2f}" in result.stdout


def test_cli_loader_harvest_system_defaults_adv2n26() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-productivity",
            "--machine-role",
            "loader",
            "--harvest-system-id",
            "steep_tethered",
        ],
    )
    assert result.exit_code == 0, result.stdout
    expected = estimate_clambunk_productivity_adv2n26(
        travel_empty_distance_m=320.0,
        stems_per_cycle=18.0,
        average_stem_volume_m3=1.35,
        utilization=0.77,
    )
    assert f"{expected.productivity_m3_per_smh:.2f}" in result.stdout
