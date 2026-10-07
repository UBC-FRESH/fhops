import json
import re
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.planning import rolling as rolling_module
from tests.cli import cli_text


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


def _failing_driver(real, fail_from_call: int, *, error: bool = False):  # type: ignore[no-untyped-def]
    """Driver stand-in returning no solution (``outcome="error"`` with ``error``) from a call on."""

    calls = {"n": 0}

    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] < fail_from_call:
            return real(*args, **kwargs)
        return {
            "objective": None,
            "production": 0.0,
            "assignments": pd.DataFrame(
                columns=["machine_id", "block_id", "day", "shift_id", "assigned", "production"]
            ),
            "has_solution": False,
            "outcome": "error" if error else "no_solution",
            "solver_status": "error" if error else "aborted",
            "termination_condition": "error" if error else "maxTimeLimit",
            "solver_error": "ApplicationError: solver crashed" if error else None,
            "warnings": [],
        }

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
        _failing_driver(rolling_module.solve_operational_milp, fail_from_call=2),
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
        _failing_driver(rolling_module.solve_operational_milp, fail_from_call=2),
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


def _plan_args(*extra: str) -> list[str]:
    return ["plan", "rolling", "examples/tiny7/scenario.yaml", *extra]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--master-days", "8", "--sub-days", "4", "--lock-days", "2"], "exceed the base scenario"),
        (["--master-days", "7", "--sub-days", "4", "--lock-days", "0"], "lock_days must be >= 1"),
        (["--master-days", "7", "--sub-days", "2", "--lock-days", "3"], "subproblem_days must be"),
        (["--master-days", "0", "--sub-days", "2", "--lock-days", "1"], "master_days must be"),
        (
            ["--master-days", "7", "--sub-days", "4", "--lock-days", "2", "--max-iterations", "0"],
            "0 is not in the range x>=1",
        ),
        (
            ["--master-days", "7", "--sub-days", "4", "--lock-days", "2", "--max-iterations", "-1"],
            "-1 is not in the range x>=1",
        ),
        (
            ["--master-days", "7", "--sub-days", "4", "--lock-days", "2", "--solver", "nope"],
            "Unsupported solver",
        ),
        (
            ["--master-days", "7", "--sub-days", "4", "--lock-days", "2", "--solver", "mip"]
            + ["--mip-solver", "nosuchsolver"],
            "is not available",
        ),
    ],
)
def test_rolling_plan_usage_errors_exit_2(args: list[str], message: str) -> None:
    result = CliRunner().invoke(app, _plan_args(*args), prog_name="fhops")
    text = cli_text(result)
    assert result.exit_code == 2, text
    assert "Traceback" not in text
    assert message in " ".join(re.sub(r"[│╭╮╰╯─]", " ", text).split())


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_rolling_plan_exits_1_when_no_window_has_a_solution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rolling_module,
        "solve_operational_milp",
        _failing_driver(rolling_module.solve_operational_milp, fail_from_call=1, error=True),
    )
    result = CliRunner().invoke(app, _rolling_args(tmp_path, "mip"), prog_name="fhops")

    text = cli_text(result)
    assert result.exit_code == 1, text
    assert "no window returned a solution" in text
    assert "ApplicationError: solver crashed" in text
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["error"] == "no window returned a solution"
    assert summary["no_solution_windows"] == len(summary["iterations"]) == 4
    assert {it["error"] for it in summary["iterations"]} == {"ApplicationError: solver crashed"}


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_rolling_plan_fail_flags_on_empty_windows(tmp_path: Path) -> None:
    empty = CliRunner().invoke(
        app, _rolling_args(tmp_path, "stub", "--fail-on-empty-window"), prog_name="fhops"
    )
    assert empty.exit_code == 1, cli_text(empty)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert "empty window" in summary["error"]
    assert len(summary["iterations"]) == 1

    no_solution_only = CliRunner().invoke(
        app, _rolling_args(tmp_path, "stub", "--fail-on-no-solution"), prog_name="fhops"
    )
    assert no_solution_only.exit_code == 0, cli_text(no_solution_only)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["empty_windows"] == 4
    assert summary["metadata"]["fail_on_no_solution"] is True


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_rolling_plan_fail_on_no_solution_stops_on_no_solution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rolling_module,
        "solve_operational_milp",
        _failing_driver(rolling_module.solve_operational_milp, fail_from_call=2),
    )
    result = CliRunner().invoke(
        app, _rolling_args(tmp_path, "mip", "--fail-on-no-solution"), prog_name="fhops"
    )
    assert result.exit_code == 1, cli_text(result)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert [it["status"] for it in summary["iterations"]] == ["solved", "no_solution"]
    assert "fail_on_no_solution=True" in summary["error"]


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize("flag", [None, "--no-mip-earliness"])
def test_rolling_plan_mip_earliness_flag(tmp_path: Path, flag: str | None) -> None:
    extra = [flag] if flag else []
    result = CliRunner().invoke(app, _rolling_args(tmp_path, "mip", *extra), prog_name="fhops")
    assert result.exit_code == 0, cli_text(result)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["metadata"]["mip_earliness"] is (flag is None)
    notes = [
        w for it in summary["iterations"] for w in it["warnings"] if w.startswith("earliness=")
    ]
    assert bool(notes) is (flag is None)
