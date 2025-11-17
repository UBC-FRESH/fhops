from __future__ import annotations

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    estimate_cable_yarder_productivity_lee2018_uphill,
    estimate_cable_yarder_productivity_tr125_single_span,
    estimate_cable_yarder_productivity_tr127,
    estimate_running_skyline_productivity_mcneel2000,
    estimate_standing_skyline_productivity_aubuchon1979,
)

runner = CliRunner()


def test_cli_skyline_lee_uphill() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "lee-uphill",
            "--slope-distance-m",
            "400",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_cable_yarder_productivity_lee2018_uphill(
        yarding_distance_m=400.0, payload_m3=0.57
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_skyline_tr125_single() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "tr125-single-span",
            "--slope-distance-m",
            "250",
            "--lateral-distance-m",
            "30",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_cable_yarder_productivity_tr125_single_span(
        slope_distance_m=250.0,
        lateral_distance_m=30.0,
        payload_m3=1.6,
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_skyline_tr127_block5() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "tr127-block5",
            "--slope-distance-m",
            "365",
            "--lateral-distance-m",
            "16",
            "--num-logs",
            "3",
            "--payload-m3",
            "1.6",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_cable_yarder_productivity_tr127(
        block=5,
        payload_m3=1.6,
        slope_distance_m=365.0,
        lateral_distance_m=16.0,
        num_logs=3.0,
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_skyline_mcneel_running() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "mcneel-running",
            "--slope-distance-m",
            "200",
            "--horizontal-distance-m",
            "240",
            "--lateral-distance-m",
            "25",
            "--vertical-distance-m",
            "40",
            "--pieces-per-cycle",
            "3.5",
            "--piece-volume-m3",
            "1.7",
            "--running-yarder-variant",
            "yarder_b",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_running_skyline_productivity_mcneel2000(
        horizontal_distance_m=240.0,
        lateral_distance_m=25.0,
        vertical_distance_m=40.0,
        pieces_per_cycle=3.5,
        piece_volume_m3=1.7,
        yarder_variant="yarder_b",
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_skyline_aubuchon_standing() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "aubuchon-standing",
            "--slope-distance-m",
            "610",
            "--lateral-distance-m",
            "30",
            "--logs-per-turn",
            "3",
            "--average-log-volume-m3",
            "0.5",
            "--crew-size",
            "4",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_standing_skyline_productivity_aubuchon1979(
        slope_distance_m=610.0,
        lateral_distance_m=30.0,
        logs_per_turn=3.0,
        average_log_volume_m3=0.5,
        crew_size=4.0,
    )
    assert f"{expected:.2f}" in result.stdout
