from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.dataset import dataset_app

runner = CliRunner()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_dataset(tmp_path: Path) -> Path:
    scenario_dir = tmp_path / "scenario"
    _write(
        scenario_dir / "blocks.csv",
        "id,landing_id,work_required\nB1,L1,5\n",
    )
    _write(
        scenario_dir / "landings.csv",
        "id,daily_capacity\nL1,1\n",
    )
    _write(
        scenario_dir / "machines.csv",
        "id,crew,daily_hours,operating_cost,role,repair_usage_hours\n"
        "Y1,C1,24,0,grapple_skidder,5000\n",
    )
    _write(
        scenario_dir / "calendar.csv",
        "machine_id,day,available\nY1,1,1\n",
    )
    _write(
        scenario_dir / "production_rates.csv",
        "machine_id,block_id,rate\nY1,B1,2\n",
    )
    scenario_yaml = scenario_dir / "scenario.yaml"
    _write(
        scenario_yaml,
        "name: dataset-cost\n"
        "num_days: 1\n"
        "data:\n"
        "  blocks: blocks.csv\n"
        "  machines: machines.csv\n"
        "  landings: landings.csv\n"
        "  calendar: calendar.csv\n"
        "  prod_rates: production_rates.csv\n",
    )
    return scenario_yaml


def _build_loader_dataset(tmp_path: Path) -> Path:
    scenario_dir = tmp_path / "loader_scenario"
    _write(
        scenario_dir / "blocks.csv",
        "id,landing_id,work_required,harvest_system_id\nB1,L1,5,ground_fb_loader_liveheel\n",
    )
    _write(
        scenario_dir / "landings.csv",
        "id,daily_capacity\nL1,1\n",
    )
    _write(
        scenario_dir / "machines.csv",
        "id,crew,daily_hours,operating_cost,role,repair_usage_hours\n"
        "L1,C2,24,0,loader,8000\n",
    )
    _write(
        scenario_dir / "calendar.csv",
        "machine_id,day,available\nL1,1,1\n",
    )
    _write(
        scenario_dir / "production_rates.csv",
        "machine_id,block_id,rate\nL1,B1,3\n",
    )
    scenario_yaml = scenario_dir / "scenario.yaml"
    _write(
        scenario_yaml,
        "name: loader-cost\n"
        "num_days: 1\n"
        "data:\n"
        "  blocks: blocks.csv\n"
        "  machines: machines.csv\n"
        "  landings: landings.csv\n"
        "  calendar: calendar.csv\n"
        "  prod_rates: production_rates.csv\n",
    )
    return scenario_yaml


def test_estimate_cost_reads_dataset_machine_usage(tmp_path: Path) -> None:
    scenario_yaml = _build_dataset(tmp_path)
    result = runner.invoke(
        dataset_app,
        [
            "estimate-cost",
            "--dataset",
            str(scenario_yaml),
            "--machine",
            "Y1",
            "--productivity",
            "25",
            "--utilisation",
            "0.85",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Machine Role" in result.stdout and "grapple_skidder" in result.stdout
    assert "Repair Usage Hours (dataset)" in result.stdout
    assert "5,000" in result.stdout


def test_inspect_machine_shows_default_rental_breakdown(tmp_path: Path) -> None:
    scenario_yaml = _build_dataset(tmp_path)
    json_path = tmp_path / "machine.json"
    result = runner.invoke(
        dataset_app,
        [
            "inspect-machine",
            "--dataset",
            str(scenario_yaml),
            "--system",
            "ctl",
            "--machine",
            "Y1",
            "--no-interactive",
            "--json-out",
            str(json_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Default Rental Breakdown" in result.stdout
    assert "Default Owning" in result.stdout
    data = json.loads(json_path.read_text())
    assert data["machine"]["id"] == "Y1"
    assert data["default_rental"]["repair_usage_hours"] == 5000


def test_inspect_machine_role_shortcut() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "inspect-machine",
            "--machine-role",
            "loader_barko450",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "loader_barko450" in result.stdout
    assert "Default Rental Rate" in result.stdout


def test_inspect_machine_tr45_roles() -> None:
    for role in ("loader_cat966c_tr45", "skidder_tr45", "bulldozer_tr45"):
        result = runner.invoke(
            dataset_app,
            [
                "inspect-machine",
                "--machine-role",
                role,
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert role in result.stdout
        assert "Default Rental Rate" in result.stdout


def test_inspect_machine_ground_fb_loader_liveheel_cost_role(tmp_path: Path) -> None:
    scenario_yaml = _build_loader_dataset(tmp_path)
    result = runner.invoke(
        dataset_app,
        [
            "inspect-machine",
            "--dataset",
            str(scenario_yaml),
            "--system",
            "ground_fb_loader_liveheel",
            "--machine",
            "L1",
            "--no-interactive",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Cost Role Override" in result.stdout
    assert "loader_barko450" in result.stdout


def test_cli_estimate_road_cost() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-road-cost",
            "--machine",
            "caterpillar_235_hydraulic_backhoe",
            "--road-length-m",
            "120",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Caterpillar 235 hydraulic backhoe" in result.stdout
    assert "Unit cost" in result.stdout
    assert "Mobilisation" in result.stdout


def test_estimate_cost_with_road_addon() -> None:
    result = runner.invoke(
        dataset_app,
        [
            "estimate-cost",
            "--machine-role",
            "grapple_skidder",
            "--productivity",
            "25",
            "--utilisation",
            "0.9",
            "--road-machine",
            "caterpillar_235_hydraulic_backhoe",
            "--road-length-m",
            "150",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "TR-28 Road Cost Estimate" in result.stdout
    assert "Soil-protection reminder" in result.stdout
