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
    assert sa_row.get("operators_config") == baseline["operators_config"]
