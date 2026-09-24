import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from fhops.cli.main import app


def test_rolling_plan_stub_exports(tmp_path: Path) -> None:
    runner = CliRunner()
    summary_path = tmp_path / "summary.json"
    assignments_path = tmp_path / "locks.csv"
    iterations_jsonl = tmp_path / "iterations.jsonl"
    iterations_csv = tmp_path / "iterations.csv"

    result = runner.invoke(
        app,
        [
            "plan",
            "rolling",
            "examples/tiny7/scenario.yaml",
            "--master-days",
            "7",
            "--sub-days",
            "7",
            "--lock-days",
            "7",
            "--solver",
            "stub",
            "--out-json",
            str(summary_path),
            "--out-assignments",
            str(assignments_path),
            "--out-iterations-jsonl",
            str(iterations_jsonl),
            "--out-iterations-csv",
            str(iterations_csv),
        ],
        prog_name="fhops",
    )

    assert result.exit_code == 0

    summary = json.loads(summary_path.read_text())
    assert isinstance(summary.get("iterations"), list)

    assignments_df = pd.read_csv(assignments_path)
    assert {"machine_id", "block_id", "day"}.issubset(assignments_df.columns)

    iterations_df = pd.read_csv(iterations_csv)
    assert "iteration_index" in iterations_df.columns
    assert iterations_jsonl.exists()


def test_tactical_operational_plan_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    summary_path = tmp_path / "tactical.json"
    harvest_path = tmp_path / "harvest.csv"
    production_path = tmp_path / "production.csv"
    flows_path = tmp_path / "flows.csv"
    purchases_path = tmp_path / "purchases.csv"
    inventory_path = tmp_path / "inventory.csv"

    result = runner.invoke(
        app,
        [
            "plan",
            "tactical-operational",
            "tests/fixtures/tactical_operational/topm-mini/specification.yaml",
            "--harvest-mode",
            "semi_continuous",
            "--demand-basis",
            "target",
            "--solver",
            "highs",
            "--time-limit",
            "30",
            "--out-json",
            str(summary_path),
            "--out-harvest-csv",
            str(harvest_path),
            "--out-production-csv",
            str(production_path),
            "--out-flows-csv",
            str(flows_path),
            "--out-purchases-csv",
            str(purchases_path),
            "--out-inventory-csv",
            str(inventory_path),
        ],
        prog_name="fhops",
    )

    assert result.exit_code == 0
    payload = json.loads(summary_path.read_text())
    assert payload["objective"] == pytest.approx(24130.0)
    assert payload["termination_condition"].lower() == "optimal"

    harvest_df = pd.read_csv(harvest_path)
    production_df = pd.read_csv(production_path)
    flows_df = pd.read_csv(flows_path)
    purchases_df = pd.read_csv(purchases_path)
    inventory_df = pd.read_csv(inventory_path)
    assert {"option_id", "harvested_area_ha", "discounted_cost"}.issubset(harvest_df.columns)
    assert {"option_id", "product_id", "volume_m3"}.issubset(production_df.columns)
    assert {"arc_id", "product_id", "volume_m3", "transport_cost"}.issubset(flows_df.columns)
    assert purchases_df.empty or {"source_id", "volume_m3", "purchase_cost"}.issubset(
        purchases_df.columns
    )
    assert {"facility_id", "product_id", "period_id", "closing_m3"}.issubset(inventory_df.columns)


def test_rolling_plan_mip_solver_options(tmp_path: Path) -> None:
    runner = CliRunner()
    summary_path = tmp_path / "summary.json"

    result = runner.invoke(
        app,
        [
            "plan",
            "rolling",
            "examples/tiny7/scenario.yaml",
            "--master-days",
            "7",
            "--sub-days",
            "7",
            "--lock-days",
            "7",
            "--solver",
            "mip",
            "--mip-solver",
            "highs",
            "--mip-solver-option",
            "mip_rel_gap=0.2",
            "--mip-time-limit",
            "30",
            "--out-json",
            str(summary_path),
        ],
        prog_name="fhops",
    )

    assert result.exit_code == 0

    summary = json.loads(summary_path.read_text())
    metadata = summary.get("metadata", {})
    assert metadata.get("mip_solver") == "highs"
    assert metadata.get("mip_solver_options", {}).get("mip_rel_gap") == 0.2
