import json
from pathlib import Path

import pandas as pd
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


def test_rolling_plan_exports_shift_ids_and_carried_state(tmp_path: Path) -> None:
    runner = CliRunner()
    summary_path = tmp_path / "summary.json"
    assignments_path = tmp_path / "locks.csv"

    result = runner.invoke(
        app,
        [
            "plan",
            "rolling",
            "examples/tiny7/scenario.yaml",
            "--master-days",
            "7",
            "--sub-days",
            "4",
            "--lock-days",
            "2",
            "--solver",
            "sa",
            "--sa-iters",
            "30",
            "--out-json",
            str(summary_path),
            "--out-assignments",
            str(assignments_path),
        ],
        prog_name="fhops",
    )

    assert result.exit_code == 0, result.output
    assignments_df = pd.read_csv(assignments_path)
    assert "shift_id" in assignments_df.columns
    assert set(assignments_df["shift_id"]) == {"S1"}
    assert not assignments_df.duplicated(["machine_id", "day", "shift_id"]).any()
    iterations = json.loads(summary_path.read_text())["iterations"]
    starts = [record["remaining_work_start"] for record in iterations]
    assert all(record["runtime_s"] is not None for record in iterations)
    assert starts == sorted(starts, reverse=True)
