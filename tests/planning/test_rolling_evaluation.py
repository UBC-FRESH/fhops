import pytest

from fhops.planning import RollingPlanResult, compute_rolling_kpis
from fhops.planning.rolling import rolling_assignments_dataframe, solve_rolling_plan
from fhops.scenario.io import load_scenario


def test_rolling_assignments_dataframe_includes_metadata_when_requested() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    result = solve_rolling_plan(
        scenario,
        master_days=7,
        subproblem_days=7,
        lock_days=7,
        solver="mip",
        mip_solver="highs",
        mip_time_limit=10,
    )

    df = rolling_assignments_dataframe(result, include_metadata=True)

    assert {"machine_id", "block_id", "day", "assigned"}.issubset(df.columns)
    assert {"scenario", "solver", "master_days"}.issubset(df.columns)
    assert len(df) == len(result.locked_assignments)


def test_compute_rolling_kpis_with_baseline_returns_deltas() -> None:
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

    comparison = compute_rolling_kpis(
        scenario,
        rolling_result,
        baseline_assignments=baseline_df,
    )

    assert comparison.baseline_kpis is not None
    assert comparison.delta_totals is not None
    assert "total_production_delta" in comparison.delta_totals
    assert len(comparison.rolling_assignments) == len(rolling_result.locked_assignments)
    assert comparison.baseline_assignments is not None
    assert len(comparison.baseline_assignments) == len(baseline_df)


def test_compute_rolling_kpis_accepts_dataframe_input() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    rolling_result = solve_rolling_plan(
        scenario,
        master_days=7,
        subproblem_days=7,
        lock_days=7,
        solver="mip",
        mip_solver="highs",
        mip_time_limit=10,
    )
    rolling_df = rolling_assignments_dataframe(rolling_result, include_metadata=False)

    comparison = compute_rolling_kpis(scenario, rolling_df)

    assert comparison.baseline_kpis is None
    assert comparison.delta_totals is None
    assert len(comparison.rolling_assignments) == len(rolling_df)


def test_compute_rolling_kpis_requires_assignments() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    empty_result = RollingPlanResult(
        locked_assignments=[],
        iteration_summaries=[],
        metadata={},
        warnings=[],
    )

    with pytest.raises(ValueError):
        compute_rolling_kpis(scenario, empty_result)
