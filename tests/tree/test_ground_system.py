"""Tests for the multi-machine ground-based system simulation."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.ground_system import (
    BreakdownConfig,
    DowntimeWindow,
    GroundSystemError,
    simulate_ground_system,
    write_ground_system,
)
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
        handle.write("H5,CH5,24.0,950.0,roadside_processor\n")
        handle.write("H6,CH6,24.0,950.0,roadside_processor\n")
    calendar = root / "scenario" / "data" / "calendar.csv"
    with calendar.open("a", encoding="utf-8") as handle:
        for machine in ("H2", "H3", "H4", "H5", "H6"):
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


def test_ground_system_processor_stage(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    result = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        processor_machine_ids=("H5", "H6"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
    )
    assert result.processor_machine_id == "H5"
    assert "H5" in result.machine_summaries
    assert "H6" in result.machine_summaries
    processor_events = [event for event in result.events if event.machine in {"H5", "H6"}]
    loader_events = [event for event in result.events if event.machine == "H4"]
    assert processor_events
    assert loader_events
    assert min(event.start_s for event in loader_events) >= min(
        event.end_s for event in processor_events
    )
    assert result.rate_provenance["processor"]["model"] == "tn103_area_a"


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
        landing_capacity_m3=5.0,
    )
    assert result.truck_summary is not None
    assert result.truck_summary["dispatched_loads"] > 0
    assert result.truck_events
    assert 0 < result.landing_inventory_max_m3 <= 5.0
    assert not any("Landing inventory peaked" in warning for warning in result.warnings)


def test_ground_system_downtime_window(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    baseline = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
        shift_days=2,
        shifts_per_day=1,
        hours_per_shift=0.25,
    )
    delayed = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
        shift_days=2,
        shifts_per_day=1,
        hours_per_shift=0.25,
        downtime=(DowntimeWindow("H2", start_s=0.0, duration_s=600.0, reason="test delay"),),
    )
    assert delayed.downtime_windows
    assert delayed.makespan_s >= baseline.makespan_s
    assert delayed.rate_provenance["schedule"]["downtime"][0]["machine_id"] == "H2"


def test_ground_system_processor_model_selection(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    result = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        processor_machine_ids=("H5", "H6"),
        processor_model="custom",
        processor_rate_m3_per_smh=100.0,
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
    )
    assert result.rate_provenance["processor"]["model"] == "custom"
    assert result.rate_provenance["processor"]["machines"]["H5"]["productivity_m3_per_smh"] == 100.0


def test_ground_system_stochastic_breakdowns(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    result = simulate_ground_system(
        scenario,
        block_id="B01",
        feller_machine_id="H1",
        skidder_machine_ids=("H2", "H3"),
        loader_machine_id="H4",
        bunch_volume_m3=1.0,
        shift_days=4,
        shifts_per_day=1,
        hours_per_shift=0.5,
        breakdown_config=BreakdownConfig(
            failure_rate_per_machine_hour=1.0,
            repair_mean_hours=0.1,
            repair_cv=0.2,
            seed=7,
        ),
    )
    assert result.breakdown_summary is not None
    assert result.breakdown_summary["failure_count"] > 0
    assert result.downtime_windows
    assert all(window.reason == "breakdown" for window in result.downtime_windows)
    assert result.rate_provenance["schedule"]["breakdowns"]["seed"] == 7


def test_ground_system_truck_shift_and_arrival_stagger(tmp_path: Path) -> None:
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
        hours_per_shift=0.5,
        truck_capacity_m3=1.0,
        truck_cycle_time_s=60.0,
        truck_count=2,
        truck_load_time_s=30.0,
        truck_arrival_interval_s=600.0,
        landing_capacity_m3=5.0,
    )
    assert result.truck_summary is not None
    assert result.truck_summary["arrival_interval_s"] == 600.0
    truck_loads = [event for event in result.truck_events if event.type == "truck_load"]
    assert truck_loads
    for event in truck_loads:
        assert any(start <= event.start_s <= end for start, end in result.shift_windows)


def test_ground_system_truck_route_and_mill_queue(tmp_path: Path) -> None:
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
        hours_per_shift=0.5,
        truck_capacity_m3=1.0,
        truck_cycle_time_s=60.0,
        truck_count=2,
        truck_load_time_s=30.0,
        truck_route_distance_m=1000.0,
        truck_speed_mps=10.0,
        mill_service_s=120.0,
        mill_bays=1,
        landing_capacity_m3=5.0,
    )
    assert result.truck_summary is not None
    assert result.truck_summary["one_way_distance_m"] == 1000.0
    assert result.truck_summary["mill_bays"] == 1
    assert result.truck_summary["mill_wait_s"] >= 0
    assert result.truck_events


def test_ground_system_processor_specs_cli(tmp_path: Path) -> None:
    scenario = _system_scenario(tmp_path)
    specs = tmp_path / "processor_specs.json"
    specs.write_text(
        json.dumps(
            {
                "H5": {"seconds_per_m3": 72.0, "fixed_s": 30.0},
                "H6": {"seconds_per_m3": 36.0, "fixed_s": 30.0},
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "specs-system"
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
            "--processor",
            "H5",
            "--processor",
            "H6",
            "--processor-specs",
            str(specs),
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
    processor = payload["rate_provenance"]["processor"]
    assert processor["model"] == "custom_specs"
    assert processor["machines"]["H5"]["productivity_m3_per_smh"] == 50.0


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
