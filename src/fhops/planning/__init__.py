"""Planning utilities beyond single-horizon solves.

This package houses helpers that assemble multi-stage planning workflows (e.g., rolling-horizon
replanning). Modules here should provide both library-friendly entry points and CLI wiring so the
same orchestration logic can be reused by automation scripts and user-facing commands.
"""

from fhops.planning.reporting import (
    RollingPlanComparison,
    comparison_dataframe,
    evaluate_rolling_plan,
    rolling_assignments_dataframe,
)
from fhops.planning.rolling import (
    RollingHorizonConfig,
    RollingInfeasibleError,
    RollingIterationPlan,
    RollingIterationSummary,
    RollingKPIComparison,
    RollingPlanResult,
    SolverOutput,
    compute_rolling_kpis,
    get_solver_hook,
    run_rolling_horizon,
    slice_scenario_for_window,
    solve_rolling_plan,
    summarize_plan,
)

__all__ = [
    "RollingPlanComparison",
    "RollingHorizonConfig",
    "RollingIterationPlan",
    "RollingIterationSummary",
    "RollingPlanResult",
    "RollingKPIComparison",
    "RollingInfeasibleError",
    "SolverOutput",
    "solve_rolling_plan",
    "get_solver_hook",
    "run_rolling_horizon",
    "slice_scenario_for_window",
    "summarize_plan",
    "compute_rolling_kpis",
    "rolling_assignments_dataframe",
    "evaluate_rolling_plan",
    "comparison_dataframe",
]
