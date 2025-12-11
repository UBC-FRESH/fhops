"""Planning utilities beyond single-horizon solves.

This package houses helpers that assemble multi-stage planning workflows (e.g., rolling-horizon
replanning). Modules here should provide both library-friendly entry points and CLI wiring so the
same orchestration logic can be reused by automation scripts and user-facing commands.
"""

from fhops.planning.rolling import (
    RollingHorizonConfig,
    RollingInfeasibleError,
    RollingIterationPlan,
    RollingIterationSummary,
    RollingPlanResult,
    SolverOutput,
    run_rolling_horizon,
    slice_scenario_for_window,
    summarize_plan,
)

__all__ = [
    "RollingHorizonConfig",
    "RollingIterationPlan",
    "RollingIterationSummary",
    "RollingPlanResult",
    "RollingInfeasibleError",
    "SolverOutput",
    "run_rolling_horizon",
    "slice_scenario_for_window",
    "summarize_plan",
]
