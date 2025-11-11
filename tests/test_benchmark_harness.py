import json
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from fhops.cli.benchmarks import run_benchmark_suite
from fhops.scenario.synthetic import SyntheticDatasetConfig, generate_random_dataset


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
    for column in [
        "solver_category",
        "best_heuristic_solver",
        "best_heuristic_objective",
        "best_heuristic_runtime_s",
        "objective_gap_vs_best_heuristic",
        "runtime_ratio_vs_best_heuristic",
    ]:
        assert column in loaded.columns

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
    assert sa_row["solver_category"] == "heuristic"
    assert sa_row["best_heuristic_solver"] == "sa"
    assert pytest.approx(sa_row["objective"], rel=1e-6) == sa_row["best_heuristic_objective"]
    assert pytest.approx(0.0, abs=1e-9) == sa_row["objective_gap_vs_best_heuristic"]
    assert pytest.approx(1.0, rel=1e-6) == sa_row["runtime_ratio_vs_best_heuristic"]
    assert mip_row["solver_category"] == "exact"
    assert mip_row["best_heuristic_solver"] == "sa"
    assert pytest.approx(sa_row["objective"], rel=1e-6) == mip_row["best_heuristic_objective"]
    assert mip_row["objective_gap_vs_best_heuristic"] < 0  # MIP outperforms heuristic
    assert mip_row["runtime_ratio_vs_best_heuristic"] > 1.0


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
    assert set(summary["best_heuristic_solver"].dropna()) == {"sa"}
    tabu_row = summary[summary["solver"] == "tabu"].iloc[0]
    assert tabu_row["objective_gap_vs_best_heuristic"] > 0
    assert (
        pytest.approx(1.0, rel=1e-6)
        == summary[summary["solver"] == "sa"].iloc[0]["runtime_ratio_vs_best_heuristic"]
    )


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
    assert all(sa_rows["best_heuristic_solver"] == "sa")


def test_synthetic_small_benchmark_kpi_bounds(tmp_path):
    summary = run_benchmark_suite(
        [Path("examples/synthetic/small/scenario.yaml")],
        tmp_path,
        time_limit=5,
        sa_iters=100,
        include_mip=False,
    )
    assert not summary.empty
    sa_row = summary.iloc[0]
    assert sa_row["scenario_path"].endswith("examples/synthetic/small/scenario.yaml")
    assert sa_row["kpi_total_production"] > 0
    assert 0 <= sa_row["kpi_utilisation_ratio_mean_shift"] <= 1.01
    assert 0 <= sa_row["kpi_utilisation_ratio_mean_day"] <= 1.01

    util_by_machine = json.loads(sa_row["kpi_utilisation_ratio_by_machine"])
    for value in util_by_machine.values():
        assert 0 <= value <= 1.01

    util_by_role = json.loads(sa_row["kpi_utilisation_ratio_by_role"])
    for value in util_by_role.values():
        assert 0 <= value <= 1.01

    assert sa_row["kpi_completed_blocks"] >= 1


@settings(max_examples=4, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(seed_value=st.integers(min_value=1, max_value=500))
def test_synthetic_kpi_properties(seed_value: int, tmp_path):
    config = SyntheticDatasetConfig(
        name="synthetic-hypo",
        tier="small",
        num_blocks=(5, 6),
        num_days=(6, 7),
        num_machines=(2, 3),
        blackout_probability=0.05,
        availability_probability=0.85,
    )
    bundle = generate_random_dataset(config, seed=seed_value)
    scenario_dir = tmp_path / f"scenario_{seed_value}"
    bundle.write(scenario_dir)

    bench_dir = tmp_path / f"bench_{seed_value}"
    summary = run_benchmark_suite(
        [scenario_dir / "scenario.yaml"],
        bench_dir,
        time_limit=5,
        sa_iters=40,
        include_mip=False,
    )
    row = summary.iloc[0]
    assert row["kpi_total_production"] >= row["kpi_completed_blocks"]
    assert 0.0 <= row["kpi_utilisation_ratio_mean_shift"] <= 1.01
    assert 0.0 <= row["kpi_utilisation_ratio_mean_day"] <= 1.01
