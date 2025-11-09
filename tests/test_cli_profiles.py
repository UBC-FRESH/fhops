from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.cli.profiles import DEFAULT_PROFILES, get_profile, merge_profile_with_cli

runner = CliRunner()


def test_get_profile_default():
    profile = get_profile("default")
    assert profile.name == "default"
    assert profile.sa.operator_presets == ("balanced",)
    assert profile.description


def test_merge_profile_respects_overrides():
    profile = DEFAULT_PROFILES["explore"]
    combined_ops, weights, batch, workers, multistart, extra = merge_profile_with_cli(
        profile.sa,
        None,
        {"swap": 2.0},
        ["move"],
        batch_neighbours=1,
        parallel_workers=1,
        parallel_multistart=1,
    )
    assert set(combined_ops or []) == {
        "swap",
        "move",
        "block_insertion",
        "cross_exchange",
        "mobilisation_shake",
    }
    assert pytest.approx(weights["swap"]) == 2.0
    assert batch == 1
    assert workers == 1
    assert multistart == 1
    assert extra == {}


def test_list_profiles_command(tmp_path: Path):
    out = tmp_path / "out.csv"
    result = runner.invoke(
        app,
        [
            "solve-heur",
            "examples/minitoy/scenario.yaml",
            "--out",
            str(out),
            "--iters",
            "5",
            "--list-profiles",
        ],
    )
    assert result.exit_code == 0
    for name in DEFAULT_PROFILES:
        assert name in result.stdout


def test_solve_heur_profile(tmp_path: Path):
    telemetry = tmp_path / "runs.jsonl"
    result = runner.invoke(
        app,
        [
            "solve-heur",
            "examples/minitoy/scenario.yaml",
            "--out",
            str(tmp_path / "out.csv"),
            "--iters",
            "10",
            "--profile",
            "explore",
            "--telemetry-log",
            str(telemetry),
        ],
    )
    assert result.exit_code == 0, result.stdout
    entries = telemetry.read_text().strip().splitlines()
    assert entries
    payload = json.loads(entries[-1])
    assert payload["profile"] == "explore"


def test_bench_suite_profile(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "bench",
            "suite",
            "--scenario",
            "examples/minitoy/scenario.yaml",
            "--out-dir",
            str(tmp_path / "bench"),
            "--time-limit",
            "5",
            "--no-include-mip",
            "--include-ils",
            "--include-tabu",
            "--profile",
            "mobilisation",
            "--sa-iters",
            "50",
            "--ils-iters",
            "50",
            "--tabu-iters",
            "50",
        ],
    )
    assert result.exit_code == 0, result.stdout
    summary_path = tmp_path / "bench" / "summary.json"
    data = json.loads(summary_path.read_text())
    profiles = {row.get("profile") for row in data if row["solver"] in {"sa", "ils", "tabu"}}
    assert "mobilisation" in profiles
