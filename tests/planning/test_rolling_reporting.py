import pytest

from fhops.planning import (
    RollingIterationSummary,
    RollingPlanResult,
    solve_rolling_plan,
)
from fhops.planning.reporting import (
    comparison_dataframe,
    evaluate_rolling_plan,
    rolling_assignments_dataframe,
)
from fhops.scenario.contract.models import ScheduleLock
from fhops.scenario.io import load_scenario


def _build_plan_result(locks: list[ScheduleLock]) -> RollingPlanResult:
    iteration = RollingIterationSummary(
        iteration_index=0,
        start_day=1,
        horizon_days=7,
        lock_days=7,
        locked_assignments=len(locks),
        objective=0.0,
        runtime_s=0.1,
        warnings=None,
    )
    return RollingPlanResult(
        locked_assignments=list(locks),
        iteration_summaries=[iteration],
        metadata={"scenario": "tiny7", "solver": "sa", "master_days": 7},
        warnings=[],
    )


def test_rolling_assignments_dataframe_shape() -> None:
    locks = [
        ScheduleLock(machine_id="machine-1", block_id="B1", day=1),
        ScheduleLock(machine_id="machine-2", block_id="B2", day=2),
    ]
    result = _build_plan_result(locks)

    df = rolling_assignments_dataframe(result)
    assert list(df.columns) == ["machine_id", "block_id", "day", "assigned"]
    assert df["assigned"].sum() == len(locks)
    assert df["day"].tolist() == [1, 2]


def test_evaluate_rolling_plan_with_baseline() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    baseline_result = solve_rolling_plan(
        scenario,
        master_days=7,
        subproblem_days=7,
        lock_days=7,
        solver="mip",
        mip_solver="highs",
        mip_time_limit=10,
    )
    baseline_df = rolling_assignments_dataframe(baseline_result, include_metadata=False)

    rolling_result = solve_rolling_plan(
        scenario,
        master_days=7,
        subproblem_days=4,
        lock_days=2,
        solver="mip",
        mip_solver="highs",
        mip_time_limit=10,
    )

    comparison = evaluate_rolling_plan(
        rolling_result,
        scenario,
        baseline_assignments=baseline_df,
        baseline_label="tiny7_full",
    )

    assert comparison.baseline_kpis is not None
    assert "total_production_delta" in comparison.deltas
    assert comparison.metadata["baseline_label"] == "tiny7_full"
    assert comparison.metadata["rolling_assignment_count"] == len(rolling_result.locked_assignments)
    assert comparison.metadata["baseline_assignment_count"] == len(baseline_df)
    assert (
        comparison.rolling_kpis["total_production"] <= comparison.baseline_kpis["total_production"]
    )

    df = comparison_dataframe(comparison, metrics=["total_production", "mobilisation_cost"])
    assert set(df.columns) == {
        "metric",
        "rolling",
        "baseline",
        "delta",
        "pct_delta",
        "baseline_label",
    }
    assert "total_production" in df["metric"].tolist()


def test_evaluate_rolling_plan_rejects_invalid_baseline() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    result = _build_plan_result([])

    with pytest.raises(TypeError):
        evaluate_rolling_plan(result, scenario, baseline_assignments="not-a-dataframe")


def test_comparison_dataframe_defaults_capture_all_metrics() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    baseline_result = solve_rolling_plan(
        scenario,
        master_days=7,
        subproblem_days=7,
        lock_days=7,
        solver="mip",
        mip_solver="highs",
        mip_time_limit=10,
    )
    baseline_df = rolling_assignments_dataframe(baseline_result, include_metadata=False)

    df = comparison_dataframe(
        evaluate_rolling_plan(
            baseline_result,
            scenario,
            baseline_assignments=baseline_df,
            baseline_label="full_baseline",
        )
    )
    assert not df.empty
    assert set(df["baseline_label"].unique()) == {"full_baseline"}

    prod_row = df[df["metric"] == "total_production"].iloc[0]
    assert prod_row["delta"] == pytest.approx(0)
    assert prod_row["pct_delta"] == pytest.approx(0)
