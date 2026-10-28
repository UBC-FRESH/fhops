"""Single-machine spatial simulation tests (P17.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_stem_models import _reconciled_scenario
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.spatial_machine import (
    Obstacle,
    SpatialMachineError,
    simulate_block,
    write_spatial_simulation,
)
from fhops.stem import build_stem_inventory

runner = CliRunner()


def test_deterministic_simulation_processes_all_trees(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    kwargs = {
        "block_id": "B01",
        "machine_id": "H1",
        "start_x_m": 881700.0,
        "start_y_m": 627500.0,
        "start_z_m": 412.0,
        "reach_radius_m": 10.0,
        "travel_speed_m_per_s": 1.0,
        "generated_utc": "2026-10-27T00:00:00+00:00",
    }
    first = simulate_block(scenario, **kwargs)
    second = simulate_block(scenario, **kwargs)

    assert first.to_dict() == second.to_dict()
    assert first.processed_count == 12
    assert first.unreachable_count == 0
    assert len({event.tree_id for event in first.events}) == 12
    assert first.total_time_s > 0
    assert first.processing_time_s > 0
    assert first.merchantable_volume_m3 > 0
    assert first.volume_status == "ok"
    assert all(event.status == "processed" for event in first.events)


def test_reach_changes_travel_distance(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    short = simulate_block(
        scenario,
        block_id="B01",
        machine_id="H1",
        start_x_m=881700.0,
        start_y_m=627500.0,
        reach_radius_m=1.0,
        travel_speed_m_per_s=1.0,
    )
    long = simulate_block(
        scenario,
        block_id="B01",
        machine_id="H1",
        start_x_m=881700.0,
        start_y_m=627500.0,
        reach_radius_m=1000.0,
        travel_speed_m_per_s=1.0,
    )

    assert short.total_distance_m > long.total_distance_m
    assert short.travel_time_s > long.travel_time_s


def test_obstacle_marks_tree_unreachable(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    stems = build_stem_inventory(scenario)
    first = stems.trees[0]
    obstacle = Obstacle(first.x_m, first.y_m, 1.0)

    result = simulate_block(
        scenario,
        block_id="B01",
        machine_id="H1",
        obstacles=(obstacle,),
    )

    assert result.unreachable_count >= 1
    assert any(
        event.tree_id == first.tree_id and event.status == "unreachable" for event in result.events
    )


def test_slope_limit_marks_trees_unreachable(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    stems = build_stem_inventory(scenario)
    first = stems.trees[0]

    result = simulate_block(
        scenario,
        block_id="B01",
        machine_id="H1",
        start_x_m=first.x_m,
        start_y_m=first.y_m,
        start_z_m=first.elevation_m,
        max_slope_percent=0.001,
    )

    assert result.unreachable_count > 0
    assert any(event.status == "unreachable" for event in result.events)


def test_unknown_block_and_machine_refuse(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    with pytest.raises(SpatialMachineError, match="Unknown block"):
        simulate_block(scenario, block_id="NOPE", machine_id="H1")
    with pytest.raises(SpatialMachineError, match="Unknown machine"):
        simulate_block(scenario, block_id="B01", machine_id="NOPE")


def test_write_outputs(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    result = simulate_block(
        scenario,
        block_id="B01",
        machine_id="H1",
        start_x_m=881700.0,
        start_y_m=627500.0,
    )

    paths = write_spatial_simulation(result, tmp_path / "sim")
    assert paths["events"].is_file()
    assert paths["manifest"].is_file()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "fhops.tree.machine_sim.v1"
    assert manifest["block_id"] == "B01"


def test_cli_simulation_writes_outputs(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    out = tmp_path / "cli-sim"

    result = runner.invoke(
        app,
        [
            "tree",
            "simulate",
            str(scenario),
            "--block",
            "B01",
            "--machine",
            "H1",
            "--start-x",
            "881700",
            "--start-y",
            "627500",
            "--out",
            str(out),
        ],
        prog_name="fhops",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["processed_count"] == 12
    assert (out / "tree_machine_events.csv").is_file()
    assert (out / "tree_machine_simulation.json").is_file()


def test_cli_obstacle_parsing_and_errors(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    result = runner.invoke(
        app,
        [
            "tree",
            "simulate",
            str(scenario),
            "--block",
            "B01",
            "--machine",
            "H1",
            "--obstacle",
            "bad",
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "Obstacle" in result.output
