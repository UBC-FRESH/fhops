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
        include_mip=False,
    )
    assert not summary.empty
    assert set(summary["solver"]) == {"sa"}

    csv_path = tmp_path / "summary.csv"
    json_path = tmp_path / "summary.json"
    assert csv_path.exists()
    assert json_path.exists()

    loaded = pd.read_csv(csv_path)
    assert "kpi_total_production" in loaded.columns
    assert loaded.iloc[0]["scenario"] == "user-1"

    baseline_path = Path("tests/fixtures/benchmarks/minitoy_sa.json")
    baseline = json.loads(baseline_path.read_text())
    row = summary.iloc[0].to_dict()
    for key in ["objective", "kpi_total_production", "kpi_completed_blocks", "iters", "seed"]:
        assert pytest.approx(baseline[key], rel=1e-6, abs=1e-6) == row[key]
