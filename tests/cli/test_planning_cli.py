import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.planning import rolling as rolling_module


@pytest.mark.filterwarnings("ignore::UserWarning")
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


@pytest.mark.filterwarnings("ignore::UserWarning")
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


def _flaky(real, fail_from_call: int):  # type: ignore[no-untyped-def]
    calls = {"n": 0}

    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] >= fail_from_call:
            raise RuntimeError("A feasible solution was not found")
        return real(*args, **kwargs)

    return wrapper


def _rolling_args(tmp_path: Path, solver: str, *extra: str) -> list[str]:
    return [
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
        solver,
        "--sa-iters",
        "30",
        "--mip-solver",
        "highs",
        "--mip-time-limit",
        "10",
        "--out-json",
        str(tmp_path / "summary.json"),
        "--out-assignments",
        str(tmp_path / "locks.csv"),
        "--out-iterations-jsonl",
        str(tmp_path / "iterations.jsonl"),
        "--out-iterations-csv",
        str(tmp_path / "iterations.csv"),
        *extra,
    ]


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_rolling_plan_fail_on_empty_window_writes_partial_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rolling_module,
        "solve_operational_milp",
        _flaky(rolling_module.solve_operational_milp, fail_from_call=2),
    )
    result = CliRunner().invoke(
        app, _rolling_args(tmp_path, "mip", "--fail-on-empty-window"), prog_name="fhops"
    )

    assert result.exit_code == 1, result.output
    assert "Rolling plan failed" in result.output
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert "Iteration 1 (days 3-6)" in summary["error"]
    assert [it["status"] for it in summary["iterations"]] == ["solved", "no_solution"]
    assert summary["no_solution_windows"] == 1
    assert summary["metadata"]["fail_on_empty_window"] is True
    locks = pd.read_csv(tmp_path / "locks.csv")
    assert len(locks) == summary["total_locked_assignments"] > 0
    assert {"shift_id", "production"} <= set(locks.columns)
    assert set(locks["day"]) <= {1, 2}
    assert len(pd.read_csv(tmp_path / "iterations.csv")) == 2
    assert len((tmp_path / "iterations.jsonl").read_text().splitlines()) == 2


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_rolling_plan_records_windows_without_solution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rolling_module,
        "solve_operational_milp",
        _flaky(rolling_module.solve_operational_milp, fail_from_call=2),
    )
    result = CliRunner().invoke(app, _rolling_args(tmp_path, "mip"), prog_name="fhops")

    assert result.exit_code == 0, result.output
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert [it["status"] for it in summary["iterations"]] == [
        "solved",
        "no_solution",
        "no_solution",
        "no_solution",
    ]
    assert summary["no_solution_window_indices"] == [1, 2, 3]
    assert summary["empty_windows"] >= 3
    assert "error" not in summary
    iterations = pd.read_csv(tmp_path / "iterations.csv")
    assert {"status", "has_solution", "planned_delivered", "locked_delivered", "empty"} <= set(
        iterations.columns
    )


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_rolling_plan_writes_partial_outputs_on_unexpected_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rolling_module, "solve_sa", _flaky(rolling_module.solve_sa, 2))
    result = CliRunner().invoke(app, _rolling_args(tmp_path, "sa"), prog_name="fhops")

    assert result.exit_code == 1, result.output
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["error"].startswith("RuntimeError")
    assert len(summary["iterations"]) == 1
    locks = pd.read_csv(tmp_path / "locks.csv")
    assert len(locks) == summary["total_locked_assignments"]
    assert set(locks["day"]) <= {1, 2}
