from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.telemetry import append_jsonl, load_jsonl

runner = CliRunner()


def _write_runs(log_path: Path, count: int) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        for idx in range(count):
            payload = {
                "run_id": f"run-{idx}",
                "solver": "sa",
                "status": "ok",
            }
            handle.write(json.dumps(payload) + "\n")


def _write_step_logs(steps_dir: Path, count: int) -> None:
    steps_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(count):
        step_path = steps_dir / f"run-{idx}.jsonl"
        step_path.write_text(
            json.dumps({"run_id": f"run-{idx}", "record_type": "step"}) + "\n", encoding="utf-8"
        )


def test_telemetry_prune(tmp_path: Path):
    log_path = tmp_path / "telemetry" / "runs.jsonl"
    steps_dir = tmp_path / "telemetry" / "steps"

    _write_runs(log_path, 10)
    _write_step_logs(steps_dir, 10)

    result = runner.invoke(
        app,
        [
            "telemetry",
            "prune",
            str(log_path),
            "--keep",
            "3",
        ],
    )
    assert result.exit_code == 0, result.stdout
    remaining_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(remaining_lines) == 3
    assert json.loads(remaining_lines[0])["run_id"] == "run-7"

    for idx in range(10):
        step_file = steps_dir / f"run-{idx}.jsonl"
        if idx >= 7:
            assert step_file.exists()
        else:
            assert not step_file.exists()


def test_telemetry_prune_dry_run(tmp_path: Path):
    log_path = tmp_path / "telemetry" / "runs.jsonl"
    steps_dir = tmp_path / "telemetry" / "steps"
    _write_runs(log_path, 5)
    _write_step_logs(steps_dir, 5)

    result = runner.invoke(
        app,
        [
            "telemetry",
            "prune",
            str(log_path),
            "--keep",
            "2",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.stdout
    # ensure file unchanged
    assert len(log_path.read_text(encoding="utf-8").strip().splitlines()) == 5
    # and steps untouched
    for idx in range(5):
        assert (steps_dir / f"run-{idx}.jsonl").exists()


def test_load_jsonl(tmp_path: Path):
    log_path = tmp_path / "telemetry" / "runs.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl(log_path, {"record_type": "run", "run_id": "run-1", "solver": "sa"})
    append_jsonl(log_path, {"record_type": "step", "run_id": "run-1"})
    append_jsonl(log_path, {"record_type": "run", "run_id": "run-2", "solver": "sa"})

    df_all = load_jsonl(log_path)
    assert len(df_all) == 3
    df_runs = load_jsonl(log_path, record_type="run")
    assert len(df_runs) == 2
    assert set(df_runs["run_id"]) == {"run-1", "run-2"}
