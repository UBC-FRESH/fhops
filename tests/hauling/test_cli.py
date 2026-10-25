"""CLI tests for `fhops haul`."""

from __future__ import annotations

from pathlib import Path

from fhops.cli.main import app
from tests.cli import CliRunner, cli_text

runner = CliRunner()
SCENARIO = "examples/hauling/scenario.yaml"


def test_haul_validate_reports_dimensions() -> None:
    result = runner.invoke(app, ["haul", "validate", SCENARIO])
    assert result.exit_code == 0, cli_text(result)
    output = cli_text(result)
    assert "Hauling" in output
    assert "Log sorts" in output
    assert "Supply/demand residuals" in output


def test_haul_plan_writes_flow_files(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "haul",
            "plan",
            SCENARIO,
            "--out-dir",
            str(tmp_path),
            "--time-limit",
            "30",
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    for name in (
        "haul_flows.csv",
        "haul_truckloads.csv",
        "haul_yard_inventory.csv",
        "haul_contractor_workload.csv",
        "haul_kpis.json",
        "haul_summary.json",
    ):
        assert (tmp_path / name).exists(), name


def test_haul_schedule_from_flow_dir(tmp_path: Path) -> None:
    flow_dir = tmp_path / "flow"
    plan = runner.invoke(
        app,
        ["haul", "plan", SCENARIO, "--out-dir", str(flow_dir), "--time-limit", "30"],
    )
    assert plan.exit_code == 0, cli_text(plan)
    schedule_dir = tmp_path / "schedule"
    result = runner.invoke(
        app,
        [
            "haul",
            "schedule",
            SCENARIO,
            "--out-dir",
            str(schedule_dir),
            "--flow-dir",
            str(flow_dir),
            "--day",
            "1",
            "--solver",
            "sa",
            "--sa-iters",
            "50",
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    assert (schedule_dir / "haul_schedule.csv").exists()
    assert (schedule_dir / "haul_truck_summary.csv").exists()
    assert (schedule_dir / "haul_summary.json").exists()


def test_haul_report_reads_a_run(tmp_path: Path) -> None:
    out_dir = tmp_path / "run"
    result = runner.invoke(
        app,
        ["haul", "plan", SCENARIO, "--out-dir", str(out_dir), "--time-limit", "30"],
    )
    assert result.exit_code == 0, cli_text(result)
    report = runner.invoke(app, ["haul", "report", str(out_dir)])
    assert report.exit_code == 0, cli_text(report)
    assert "Hauling run report" in cli_text(report)


def test_haul_solve_writes_combined_run(tmp_path: Path) -> None:
    out_dir = tmp_path / "solve"
    result = runner.invoke(
        app,
        [
            "haul",
            "solve",
            SCENARIO,
            "--out-dir",
            str(out_dir),
            "--day",
            "1",
            "--solver",
            "mip",
            "--time-limit",
            "30",
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    assert (out_dir / "haul_flows.csv").exists()
    assert (out_dir / "haul_schedule.csv").exists()
    assert (out_dir / "haul_summary.json").exists()


MARINE_SCENARIO = "examples/hauling_marine/scenario.yaml"


def test_haul_validate_reports_marine_dimensions() -> None:
    result = runner.invoke(app, ["haul", "validate", MARINE_SCENARIO])
    assert result.exit_code == 0, cli_text(result)
    output = cli_text(result)
    assert "Barges" in output
    assert "Ports" in output
    assert "Marine routes" in output
    assert "road+water" in output


def test_haul_plan_and_schedule_write_marine_artefacts(tmp_path: Path) -> None:
    flow_dir = tmp_path / "flow"
    plan = runner.invoke(
        app,
        ["haul", "plan", MARINE_SCENARIO, "--out-dir", str(flow_dir), "--time-limit", "30"],
    )
    assert plan.exit_code == 0, cli_text(plan)
    for name in (
        "haul_marine_flows.csv",
        "haul_marine_truckloads.csv",
        "haul_barge_trips.csv",
        "haul_port_inventory.csv",
    ):
        assert (flow_dir / name).exists(), name
    schedule_dir = tmp_path / "schedule"
    schedule = runner.invoke(
        app,
        [
            "haul",
            "schedule",
            MARINE_SCENARIO,
            "--out-dir",
            str(schedule_dir),
            "--flow-dir",
            str(flow_dir),
            "--day",
            "1",
            "--solver",
            "mip",
            "--time-limit",
            "30",
        ],
    )
    assert schedule.exit_code == 0, cli_text(schedule)
    assert (schedule_dir / "haul_barge_schedule.csv").exists()
    assert (schedule_dir / "haul_barge_summary.csv").exists()
