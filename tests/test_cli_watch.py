from __future__ import annotations

import subprocess
from pathlib import Path


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def test_solve_heur_watch_smoke(tmp_path: Path):
    """Solver should complete even when watch mode falls back to warning."""

    out_csv = tmp_path / "watch_sa.csv"
    result = _run_command(
        [
            "fhops",
            "solve-heur",
            "examples/tiny7/scenario.yaml",
            "--iters",
            "200",
            "--cooling-rate",
            "0.999",
            "--restart-interval",
            "100",
            "--watch",
            "--watch-refresh",
            "0.1",
            "--out",
            str(out_csv),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert "Watch mode disabled" in result.stdout or "FHOPS Heuristic Watch" in result.stdout
    assert "Objective (heuristic):" in result.stdout
    assert out_csv.exists()


def test_tune_random_watch_smoke(tmp_path: Path):
    """Random tuner should finish and log telemetry with watch enabled."""

    telemetry = tmp_path / "runs.jsonl"
    result = _run_command(
        [
            "fhops",
            "tune-random",
            str(Path("examples/tiny7/scenario.yaml")),
            "--runs",
            "1",
            "--iters",
            "50",
            "--telemetry-log",
            str(telemetry),
            "--watch",
            "--watch-refresh",
            "0.1",
        ]
    )
    assert result.returncode == 0, result.stderr
    assert "Watch mode disabled" in result.stdout or "FHOPS Heuristic Watch" in result.stdout
    assert "Random tuner results" in result.stdout
    assert telemetry.exists()
