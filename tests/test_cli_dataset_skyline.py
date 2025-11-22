from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app
from fhops.productivity import (
    estimate_cable_yarder_productivity_lee2018_uphill,
    estimate_cable_yarder_productivity_tr125_single_span,
    estimate_cable_yarder_productivity_tr127,
    estimate_running_skyline_productivity_mcneel2000,
    estimate_standing_skyline_productivity_aubuchon1979,
    estimate_standing_skyline_productivity_kramer1978,
    estimate_standing_skyline_productivity_kellogg1976,
    estimate_residue_productivity_ledoux_m3_per_pmh,
    estimate_micro_master_productivity_m3_per_pmh,
    estimate_hi_skid_productivity_m3_per_pmh,
    get_tn173_system,
    estimate_tmy45_productivity_fncy12,
    Fncy12ProductivityVariant,
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


def test_cli_skyline_tr125_multi_warning_and_telemetry(tmp_path) -> None:
    telemetry_log = tmp_path / "skyline.jsonl"
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "tr125-multi-span",
            "--slope-distance-m",
            "250",
            "--lateral-distance-m",
            "40",
            "--telemetry-log",
            str(telemetry_log),
        ],
    )
    assert result.exit_code == 0
    assert "TN258 envelope" in result.stdout
    assert "Support reminder" in result.stdout
    payload = json.loads(telemetry_log.read_text(encoding="utf-8").strip())
    assert payload["tn258_lateral_limit_exceeded"] is True
    assert payload["support_cat_d8_smhr_per_yarder_smhr"] == pytest.approx(0.25)
    assert payload["support_timberjack450_smhr_per_yarder_smhr"] == pytest.approx(0.14)
    assert payload["non_bc_source"] is False


def test_cli_skyline_fncy12_variant_and_warning(tmp_path) -> None:
    telemetry_log = tmp_path / "fncy12.jsonl"
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "fncy12-tmy45",
            "--slope-distance-m",
            "320",
            "--lateral-distance-m",
            "35",
            "--fncy12-variant",
            "steady_state_no_fire",
            "--telemetry-log",
            str(telemetry_log),
        ],
    )
    assert result.exit_code == 0
    expected = estimate_tmy45_productivity_fncy12(
        Fncy12ProductivityVariant.STEADY_STATE_NO_FIRE
    ).productivity_m3_per_pmh
    assert f"{expected:.2f}" in result.stdout
    assert "TN258 envelope" in result.stdout
    payload = json.loads(telemetry_log.read_text(encoding="utf-8").strip())
    assert payload["tn258_lateral_limit_exceeded"] is True
    assert payload["fncy12_variant"] == "steady_state_no_fire"
    assert payload["support_cat_d8_smhr_per_yarder_smhr"] == pytest.approx(0.25)
    assert payload["support_timberjack450_smhr_per_yarder_smhr"] == pytest.approx(0.14)


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


def test_cli_skyline_tr127_block1_with_latd2() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "tr127-block1",
            "--slope-distance-m",
            "300",
            "--lateral-distance-m",
            "15",
            "--lateral-distance-2-m",
            "6",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_cable_yarder_productivity_tr127(
        block=1,
        slope_distance_m=300.0,
        lateral_distance_m=15.0,
        lateral_distance2_m=6.0,
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


def test_cli_skyline_manual_falling_options() -> None:
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
            "--manual-falling",
            "--manual-falling-species",
            "douglas_fir",
            "--manual-falling-dbh-cm",
            "32.5",
        ],
    )
    assert result.exit_code == 0
    assert "Manual Falling Species" in result.stdout
    assert "Manual Falling Cost (2024 CAD $/tree)" in result.stdout


def test_cli_skyline_manual_falling_defaults_from_system() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "tn173-ecologger",
            "--slope-distance-m",
            "150",
            "--lateral-distance-m",
            "20",
            "--harvest-system-id",
            "cable_micro_ecologger",
        ],
    )
    assert result.exit_code == 0
    assert "Manual Falling Species" in result.stdout
    assert "Applied manual falling defaults from harvest system" in result.stdout


def test_cli_skyline_tn173_ecologger() -> None:
    system = get_tn173_system("tn173_ecologger")
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "tn173-ecologger",
            "--slope-distance-m",
            "120",
        ],
    )
    assert result.exit_code == 0
    assert system.payload_m3 is not None
    expected = (system.payload_m3 * 60.0) / system.cycle_minutes
    assert f"{expected:.2f}" in result.stdout


def test_cli_skyline_hi_skid_yard_only() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "hi-skid",
            "--slope-distance-m",
            "30",
        ],
    )
    assert result.exit_code == 0
    expected, _, _, _, _, _ = estimate_hi_skid_productivity_m3_per_pmh(slope_distance_m=30.0)
    assert f"{expected:.2f}" in result.stdout


def test_cli_skyline_hi_skid_include_travel() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "hi-skid",
            "--slope-distance-m",
            "30",
            "--hi-skid-include-haul",
        ],
    )
    assert result.exit_code == 0
    _, overall, _, _, _, _ = estimate_hi_skid_productivity_m3_per_pmh(
        slope_distance_m=30.0,
        include_travel_minutes=30.0,
    )
    assert overall is not None
    assert f"{overall:.2f}" in result.stdout


def test_cli_skyline_hi_skid_flag_validation() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "lee-uphill",
            "--slope-distance-m",
            "100",
            "--hi-skid-include-haul",
        ],
    )
    assert result.exit_code != 0


def test_cli_skyline_harvest_system_micro_defaults() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--slope-distance-m",
            "120",
            "--harvest-system-id",
            "cable_micro_ecologger",
        ],
    )
    assert result.exit_code == 0
    assert "tn173-ecologger" in result.stdout


def test_cli_skyline_harvest_system_hi_skid() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--slope-distance-m",
            "40",
            "--harvest-system-id",
            "cable_micro_hi_skid",
        ],
    )
    assert result.exit_code == 0
    assert "hi-skid" in result.stdout


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


def test_cli_skyline_aubuchon_kramer() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "aubuchon-kramer",
            "--slope-distance-m",
            "550",
            "--lateral-distance-m",
            "35",
            "--logs-per-turn",
            "4.2",
            "--average-log-volume-m3",
            "0.45",
            "--carriage-height-m",
            "10",
            "--chordslope-percent",
            "-12",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_standing_skyline_productivity_kramer1978(
        slope_distance_m=550.0,
        lateral_distance_m=35.0,
        logs_per_turn=4.2,
        average_log_volume_m3=0.45,
        carriage_height_m=10.0,
        chordslope_percent=-12.0,
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_skyline_aubuchon_kellogg() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "aubuchon-kellogg",
            "--slope-distance-m",
            "480",
            "--lateral-distance-m",
            "25",
            "--logs-per-turn",
            "3.8",
            "--average-log-volume-m3",
            "0.4",
            "--lead-angle-deg",
            "20",
            "--chokers",
            "2",
        ],
    )
    assert result.exit_code == 0
    expected = estimate_standing_skyline_productivity_kellogg1976(
        slope_distance_m=480.0,
        lead_angle_degrees=20.0,
        logs_per_turn=3.8,
        average_log_volume_m3=0.4,
        chokers=2.0,
    )
    assert f"{expected:.2f}" in result.stdout


def test_cli_skyline_ledoux_tmy45() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "ledoux-tmy45",
            "--slope-distance-m",
            "120",
            "--merchantable-logs-per-turn",
            "1.5",
            "--merchantable-volume-m3",
            "4.2",
            "--residue-pieces-per-turn",
            "1.0",
            "--residue-volume-m3",
            "0.8",
        ],
    )
    assert result.exit_code == 0, result.stdout
    expected, _ = estimate_residue_productivity_ledoux_m3_per_pmh(
        profile="tmy45",
        slope_distance_m=120.0,
        merchantable_logs_per_turn=1.5,
        merchantable_volume_m3=4.2,
        residue_pieces_per_turn=1.0,
        residue_volume_m3=0.8,
    )
    assert f"{expected:.2f}" in result.stdout
    assert "Merchantable Delay Component" in result.stdout
    assert "Residue Delay Component" in result.stdout


def test_cli_skyline_ledoux_residue_warning() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "ledoux-tmy45",
            "--slope-distance-m",
            "150",
            "--merchantable-logs-per-turn",
            "1.0",
            "--merchantable-volume-m3",
            "2.0",
            "--residue-pieces-per-turn",
            "5.0",
            "--residue-volume-m3",
            "2.5",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Residue-heavy turn" in result.stdout


def test_cli_skyline_ledoux_requires_inputs() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "ledoux-skagit-shotgun",
            "--slope-distance-m",
            "90",
        ],
    )
    assert result.exit_code != 0
    assert "merchantable-logs" in result.stdout.lower()


def test_cli_skyline_micro_master_defaults() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "micro-master",
            "--slope-distance-m",
            "70",
        ],
    )
    assert result.exit_code == 0, result.stdout
    expected, cycle_minutes, _, _, _ = estimate_micro_master_productivity_m3_per_pmh(
        slope_distance_m=70.0
    )
    assert f"{expected:.2f}" in result.stdout
    assert f"{cycle_minutes:.2f}" in result.stdout
    assert "Micro Master" in result.stdout


def test_cli_skyline_micro_master_overrides() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--model",
            "micro-master",
            "--slope-distance-m",
            "90",
            "--pieces-per-cycle",
            "2.5",
            "--piece-volume-m3",
            "0.5",
        ],
    )
    assert result.exit_code == 0, result.stdout
    expected, _, resolved_pieces, resolved_piece_volume, payload = (
        estimate_micro_master_productivity_m3_per_pmh(
            slope_distance_m=90.0,
            pieces_per_turn=2.5,
            piece_volume_m3=0.5,
        )
    )
    assert f"{expected:.2f}" in result.stdout
    assert f"{resolved_pieces:.2f}" in result.stdout
    assert f"{resolved_piece_volume:.3f}" in result.stdout
    assert f"{payload:.2f}" in result.stdout


def test_cli_skyline_harvest_system_running_defaults() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--slope-distance-m",
            "280",
            "--lateral-distance-m",
            "20",
            "--harvest-system-id",
            "cable_running",
        ],
    )
    assert result.exit_code == 0
    assert "mcneel-running" in result.stdout
    assert "Applied productivity defaults from harvest system 'cable_running'" in result.stdout


def test_cli_skyline_harvest_system_standing_defaults() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-skyline-productivity",
            "--slope-distance-m",
            "320",
            "--lateral-distance-m",
            "30",
            "--harvest-system-id",
            "cable_standing",
        ],
    )
    assert result.exit_code == 0
    assert "aubuchon-kramer" in result.stdout
    assert "Carriage Height (m)" in result.stdout
