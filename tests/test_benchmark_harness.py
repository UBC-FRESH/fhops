import json
from pathlib import Path

import pandas as pd
import pytest

from fhops.cli.benchmarks import run_benchmark_suite


def test_benchmark_suite_minitoy(tmp_path):
    summary = run_benchmark_suite(
        [Path("examples/minitoy/scenario.yaml")],
        tmp_path,
        time_limit=10,
        sa_iters=200,
        include_mip=True,
    )
    assert not summary.empty
    assert set(summary["solver"]) == {"sa", "mip"}

    csv_path = tmp_path / "summary.csv"
    json_path = tmp_path / "summary.json"
    assert csv_path.exists()
    assert json_path.exists()

    loaded = pd.read_csv(csv_path)
    assert "kpi_total_production" in loaded.columns
    assert set(loaded["scenario"]) == {"user-1"}
    assert "operators_config" in loaded.columns
    assert "preset_label" in loaded.columns

    baseline_path = Path("tests/fixtures/benchmarks/minitoy_sa.json")
    baseline = json.loads(baseline_path.read_text())
    sa_row = summary[summary["solver"] == "sa"].iloc[0].to_dict()
    mip_row = summary[summary["solver"] == "mip"].iloc[0].to_dict()

    numeric_keys = [
        "objective",
        "kpi_total_production",
        "kpi_completed_blocks",
        "kpi_mobilisation_cost",
        "iters",
        "seed",
        "sa_initial_score",
        "sa_acceptance_rate",
        "sa_accepted_moves",
        "sa_proposals",
        "sa_restarts",
        "objective_vs_mip_gap",
        "objective_vs_mip_ratio",
    ]
    for key in numeric_keys:
        assert pytest.approx(baseline[key], rel=1e-6, abs=1e-6) == sa_row[key]

    assert pytest.approx(0.0, abs=1e-9) == mip_row["objective_vs_mip_gap"]
    assert pytest.approx(1.0, abs=1e-9) == mip_row["objective_vs_mip_ratio"]

    baseline_breakdown = json.loads(baseline["kpi_mobilisation_cost_by_machine"])
    row_breakdown = json.loads(sa_row["kpi_mobilisation_cost_by_machine"])
    assert set(row_breakdown) == set(baseline_breakdown)
    for machine, value in baseline_breakdown.items():
        assert pytest.approx(value, rel=1e-6, abs=1e-6) == row_breakdown[machine]
    assert json.loads(sa_row.get("operators_config", "{}")) == json.loads(
        baseline["operators_config"]
    )
    assert json.loads(sa_row.get("operators_stats", "{}")) == json.loads(
        baseline["operators_stats"]
    )
    assert sa_row["preset_label"] == baseline["preset_label"]


def test_benchmark_suite_with_tabu(tmp_path):
    summary = run_benchmark_suite(
        [Path("examples/minitoy/scenario.yaml")],
        tmp_path,
        time_limit=10,
        sa_iters=200,
        include_tabu=True,
        tabu_iters=200,
        include_mip=False,
    )
    solvers = set(summary["solver"])
    assert {"sa", "tabu"}.issubset(solvers)

def test_benchmark_suite_preset_comparison(tmp_path):
    summary = run_benchmark_suite(
        [Path("examples/minitoy/scenario.yaml")],
        tmp_path,
        time_limit=10,
        sa_iters=200,
        include_mip=False,
        preset_comparisons=["explore", "stabilise"],
    )
    sa_rows = summary[summary["solver"] == "sa"]
    assert len(sa_rows) == 3  # default + two comparisons
    labels = set(sa_rows["preset_label"])
    assert labels == {"default", "explore", "stabilise"}
    explore_row = sa_rows.set_index("preset_label").loc["explore"]
    config = json.loads(explore_row["operators_config"])
    assert pytest.approx(config["mobilisation_shake"], rel=1e-6) == 0.2
