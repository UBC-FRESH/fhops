"""Tests for the multi-machine ground-based system simulation."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.ground_system import GroundSystemError, simulate_ground_system, write_ground_system
from fhops.tree_mapping import register_tree_inventory

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tree_scale"


def _system_scenario(tmp_path: Path) -> Path:
    root = tmp_path / "tree_scale"
    shutil.copytree(FIXTURE, root)
    scenario = root / "scenario" / "scenario.yaml"
    machines = root / "scenario" / "data" / "machines.csv"
    with machines.open("a", encoding="utf-8") as handle:
        handle.write("H2,CH2,24.0,950.0,grapple_skidder\n")
        handle.write("H3,CH3,24.0,950.0,grapple_skidder\n")
        handle.write("H4,CH4,24.0,950.0,loader\n")
    calendar = root / "scenario" / "data" / "calendar.csv"
    with calendar.open("a", encoding="utf-8") as handle:
        for machine in ("H2", "H3", "H4"):
            for day in range(1, 8):
                handle.write(f"{machine},{day},1\n")
    register_tree_inventory(
        scenario,
        root / "tree_inventory" / "inventory.csv",
        metadata_path=root / "tree_inventory" / "inventory.meta.json",
    )
    return scenario


def test_ground_system_is_deterministic_and_conserves_trees(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    first = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
    )
    second = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
    )

    assert first.system_id == second.system_id
    assert first.tree_count == 12
    assert len({tree.tree_id for tree in first.trees}) == 12
    assert first.processed_volume_m3 == second.processed_volume_m3
    assert first.makespan_s > 0
    assert first.makespan_s >= max(first.machine_summaries["H1"]["busy_s"], 0.0)
    assert set(first.machine_summaries) == {"H1", "H2", "H3", "H4"}
    assert all(event.end_s >= event.start_s for event in first.events)
    assert sum(1 for event in first.events if event.type == "unload") == len(
        [event for event in first.events if event.type == "load"]
    )
    assert any(event.machine == "H4" and event.type == "process" for event in first.events)


def test_ground_system_calibrated_and_reference_rates(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    calibrated = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
        rate_model="calibrated",
    )
    reference = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
        rate_model="reference",
    )
    assert calibrated.rate_model == "calibrated"
    assert calibrated.rate_provenance["skidder"]["model"].startswith("Han et al.")
    assert calibrated.rate_provenance["loader"]["model"].startswith("Barko 450")
    assert reference.rate_model == "reference"
    assert reference.rate_provenance["model"].startswith("reference")
    assert calibrated.system_id != reference.system_id
    assert calibrated.makespan_s != reference.makespan_s


def test_ground_system_shift_windows_delay_work(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    result = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
        shift_days=2,
        shifts_per_day=1,
        hours_per_shift=0.25,
        shift_start_hour=0.0,
    )
    assert len(result.shift_windows) == 2
    assert result.makespan_s >= 0.25 * 3600.0
    assert result.rate_provenance["schedule"]["shift_days"] == 2


def test_ground_system_trucking_and_landing_inventory(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    result = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
        truck_capacity_m3=1.0,
        truck_cycle_time_s=60.0,
        truck_count=1,
        truck_load_time_s=30.0,
        landing_capacity_m3=2.0,
    )
    assert result.truck_summary is not None
    assert result.truck_summary["dispatched_loads"] > 0
    assert result.truck_events
    assert result.landing_inventory_max_m3 > 0
    assert any("Landing inventory peaked" in warning for warning in result.warnings)


def test_ground_system_writes_outputs(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    result = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
    )
    paths = write_ground_system(result, tmp_path / "system")
    for path in paths.values():
        assert path.is_file()

    payload = json.loads(paths["events_json"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == "fhops.tree.ground_system.v1"
    assert payload["duration_s"] == result.makespan_s
    assert payload["rate_model"] == result.rate_model
    assert "rate_provenance" in payload
    assert payload["timeline"]
    assert payload["machines"]["H4"]["type"] == "loader"
    assert len(payload["trees"]) == 12
    assert "tree_id,x_m,y_m" in paths["trees_csv"].read_text(encoding="utf-8")
    with paths["events_csv"].open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["machine"] in {"H1", "H2", "H3", "H4"} for row in rows)


def test_ground_system_rejects_unknown_machine(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    try:
        simulate_ground_system(
            scenario,
            block_id="B01",
            feller_machine_id="H1",
            skidder_machine_ids=("H2", "NOPE"),
            loader_machine_id="H4",
        )
    except GroundSystemError as exc:
        assert "Unknown scenario machine" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("Expected GroundSystemError")


def test_ground_system_cli(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    out = tmp_path / "cli-system"
    result = runner.invoke(
        app,
        [
            "tree",
            "system",
            str(scenario),
            "--block",
            "B01",
            "--feller",
            "H1",
            "--skidder",
            "H2",
            "--skidder",
            "H3",
            "--loader",
            "H4",
            "--bunch-volume",
            "1.0",
            "--out",
            str(out),
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tree_count"] == 12
    assert payload["paths"]["manifest"] == str(out / "system_summary.json")
    assert (out / "system_events.json").is_file()
