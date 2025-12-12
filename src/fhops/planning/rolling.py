"""Rolling-horizon replanning utilities.

This module provides the core planning primitives for building multi-iteration schedules: slicing a
scenario into sub-horizons, tracking locked-in assignments, and constructing iteration plans that
advance the window by a configurable lock span. Solver integration (heuristics/MILP) attaches to
these primitives so both CLI and Python callers share the same orchestration layer.

Example
-------
>>> from fhops.planning.rolling import solve_rolling_plan
>>> from fhops.scenario.io import load_scenario
>>> scenario = load_scenario("examples/tiny7/scenario.yaml")
>>> result = solve_rolling_plan(
...     scenario,
...     master_days=14,
...     subproblem_days=7,
...     lock_days=7,
...     solver="sa",
...     sa_iters=200,
... )
>>> len(result.locked_assignments)  # locked plan length across iterations
14
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from numbers import Number
from typing import Protocol

import pandas as pd

from fhops.evaluation import KPIResult, compute_kpis
from fhops.model.milp.driver import solve_operational_milp
from fhops.optimization.heuristics.sa import solve_sa
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Scenario,
    ScheduleLock,
    ShiftCalendarEntry,
)
from fhops.scheduling.mobilisation.models import BlockDistance, MobilisationConfig

__all__ = [
    "RollingHorizonConfig",
    "RollingIterationPlan",
    "RollingIterationSummary",
    "RollingPlanResult",
    "RollingKPIComparison",
    "RollingInfeasibleError",
    "StubSolver",
    "SASolver",
    "MILPSolver",
    "solve_rolling_plan",
    "get_solver_hook",
    "SolverOutput",
    "run_rolling_horizon",
    "summarize_plan",
    "build_iteration_plan",
    "slice_scenario_for_window",
    "rolling_assignments_dataframe",
    "compute_rolling_kpis",
]


@dataclass
class RollingHorizonConfig:
    """Configuration for a rolling-horizon planning run.

    Parameters
    ----------
    scenario:
        Validated scenario to slice into rolling subproblems.
    master_days:
        Total number of days to cover with locked-in plans (e.g., 84 or 112).
    subproblem_days:
        Length of each optimisation window. Must be >= ``lock_days``.
    lock_days:
        Number of days to freeze after each solve. Typically smaller than ``subproblem_days``.
    start_day:
        One-indexed day in the base scenario where the rolling window begins.
    """

    scenario: Scenario
    master_days: int
    subproblem_days: int
    lock_days: int
    start_day: int = 1

    def __post_init__(self) -> None:
        if self.master_days < 1:
            raise ValueError("master_days must be >= 1")
        if self.subproblem_days < 1:
            raise ValueError("subproblem_days must be >= 1")
        if self.lock_days < 1:
            raise ValueError("lock_days must be >= 1")
        if self.subproblem_days < self.lock_days:
            raise ValueError("subproblem_days must be >= lock_days")
        if self.start_day < 1:
            raise ValueError("start_day must be >= 1")

        max_required_day = self.start_day + self.master_days - 1
        if max_required_day > self.scenario.num_days:
            raise ValueError(
                "master_days and start_day exceed the base scenario horizon "
                f"({max_required_day} > {self.scenario.num_days})"
            )


@dataclass
class RollingIterationPlan:
    """Metadata for a single rolling-horizon iteration.

    Attributes
    ----------
    iteration_index:
        Zero-based iteration counter.
    start_day:
        One-indexed start day in the base scenario.
    horizon_days:
        Sub-horizon length (days) solved in this iteration.
    lock_days:
        Days to freeze after the solve before advancing the window.
    """

    iteration_index: int
    start_day: int
    horizon_days: int
    lock_days: int

    @property
    def end_day(self) -> int:
        """Inclusive end day of the subproblem (in base-scenario coordinates)."""

        return self.start_day + self.horizon_days - 1


def build_iteration_plan(config: RollingHorizonConfig) -> list[RollingIterationPlan]:
    """Generate iteration windows until the master horizon is covered.

    Parameters
    ----------
    config:
        Rolling-horizon configuration describing the master horizon, subproblem span, and lock step.

    Returns
    -------
    list of RollingIterationPlan
        Ordered list of iteration windows, each with a start day, horizon span, and lock span. The
        final window may use a shorter lock span if the remaining master horizon is smaller.
    """

    iterations: list[RollingIterationPlan] = []
    locked_days = 0
    current_start = config.start_day
    master_end = config.start_day + config.master_days - 1
    iteration_idx = 0

    while locked_days < config.master_days and current_start <= master_end:
        remaining = config.master_days - locked_days
        lock_span = min(config.lock_days, remaining)
        horizon_end = min(current_start + config.subproblem_days - 1, master_end)
        horizon_span = horizon_end - current_start + 1

        iterations.append(
            RollingIterationPlan(
                iteration_index=iteration_idx,
                start_day=current_start,
                horizon_days=horizon_span,
                lock_days=lock_span,
            )
        )

        locked_days += lock_span
        current_start += lock_span
        iteration_idx += 1

    return iterations


def slice_scenario_for_window(
    base: Scenario,
    window: RollingIterationPlan,
    locked_assignments: Sequence[ScheduleLock] | None = None,
) -> Scenario:
    """Return a horizon-trimmed scenario for the given iteration window.

    The slice rebases day indices so the window start maps to day 1, filters calendars/locks outside
    the window, and clamps block availability to the sub-horizon. It also trims mobilisation
    distances to the surviving block set to satisfy scenario validation.

    Parameters
    ----------
    base:
        Original scenario to slice. This object is not mutated.
    window:
        Iteration window describing the start day and sub-horizon length.
    locked_assignments:
        Optional locked assignments to inject; only those falling inside the window are retained and
        day-rebased.

    Returns
    -------
    Scenario
        A deep-copied scenario with ``num_days == window.horizon_days`` and calendars/locks rebased
        to start at day 1.
    """

    start = window.start_day
    end = window.end_day
    copy = base.model_copy(deep=True)
    copy.num_days = window.horizon_days

    if copy.start_date:
        copy.start_date = copy.start_date + timedelta(days=start - 1)

    copy.calendar = _rebase_calendar(copy.calendar, start, end)
    copy.shift_calendar = _rebase_shift_calendar(copy.shift_calendar, start, end)

    filtered_blocks, kept_blocks = _filter_and_rebase_blocks(base, start, end, window.horizon_days)
    copy.blocks = filtered_blocks
    copy.production_rates = [rate for rate in copy.production_rates if rate.block_id in kept_blocks]
    copy.mobilisation = _filter_mobilisation(copy.mobilisation, kept_blocks)

    copy.locked_assignments = _rebase_locks(
        locked_assignments or copy.locked_assignments or [], start, end
    )

    return copy


def _rebase_calendar(entries: list[CalendarEntry], start: int, end: int) -> list[CalendarEntry]:
    rebased: list[CalendarEntry] = []
    for entry in entries:
        if start <= entry.day <= end:
            rebased.append(entry.model_copy(update={"day": entry.day - start + 1}))
    return rebased


def _rebase_shift_calendar(
    entries: list[ShiftCalendarEntry] | None, start: int, end: int
) -> list[ShiftCalendarEntry] | None:
    if not entries:
        return entries
    rebased: list[ShiftCalendarEntry] = []
    for entry in entries:
        if start <= entry.day <= end:
            rebased.append(entry.model_copy(update={"day": entry.day - start + 1}))
    return rebased


def _filter_and_rebase_blocks(
    base: Scenario, start: int, end: int, horizon_days: int
) -> tuple[list[Block], set[str]]:
    filtered_blocks: list[Block] = []
    kept_ids: set[str] = set()
    for block in base.blocks:
        earliest = block.earliest_start if block.earliest_start is not None else 1
        latest = block.latest_finish if block.latest_finish is not None else base.num_days

        if latest < start or earliest > end:
            continue

        rebased = block.model_copy(deep=True)
        rebased.earliest_start = max(1, earliest - (start - 1))
        rebased.latest_finish = min(horizon_days, latest - (start - 1))
        filtered_blocks.append(rebased)
        kept_ids.add(rebased.id)
    return filtered_blocks, kept_ids


def _filter_mobilisation(
    mobilisation: MobilisationConfig | None, kept_blocks: set[str]
) -> MobilisationConfig | None:
    if mobilisation is None or mobilisation.distances is None:
        return mobilisation

    filtered_distances: list[BlockDistance] = []
    for dist in mobilisation.distances:
        if dist.from_block in kept_blocks and dist.to_block in kept_blocks:
            filtered_distances.append(dist)

    return mobilisation.model_copy(update={"distances": filtered_distances})


def _rebase_locks(locks: Sequence[ScheduleLock], start: int, end: int) -> list[ScheduleLock] | None:
    if not locks:
        return []

    rebased: list[ScheduleLock] = []
    for lock in locks:
        if start <= lock.day <= end:
            rebased.append(lock.model_copy(update={"day": lock.day - start + 1}))
    return rebased


@dataclass
class RollingIterationSummary:
    """Outcome summary for a single rolling-horizon iteration.

    Attributes
    ----------
    iteration_index :
        Zero-based iteration counter.
    start_day :
        One-indexed day in the base scenario where the sub-horizon begins.
    horizon_days :
        Number of days solved in this iteration (sub-horizon length).
    lock_days :
        Number of leading days frozen into the master plan after this solve.
    locked_assignments :
        Count of :class:`fhops.scenario.contract.models.ScheduleLock` entries injected into the
        master plan from this iteration (base-scenario coordinates).
    objective :
        Solver objective value (units match the chosen solver) or ``None`` when not reported.
    runtime_s :
        Wall-clock runtime in seconds, if the solver provides it.
    warnings :
        Optional warnings surfaced by the solver hook (e.g., termination condition).
    """

    iteration_index: int
    start_day: int
    horizon_days: int
    lock_days: int
    locked_assignments: int
    objective: float | None = None
    runtime_s: float | None = None
    warnings: list[str] | None = None


@dataclass
class RollingPlanResult:
    """Aggregated result for a rolling-horizon run.

    Attributes
    ----------
    locked_assignments :
        Locked :class:`fhops.scenario.contract.models.ScheduleLock` entries rebased to the base
        scenario (one-indexed days).
    iteration_summaries :
        Per-iteration summaries (objective, runtime, warnings, lock span, horizon span).
    metadata :
        Descriptive metadata such as scenario name, master/sub/lock horizon lengths, start day, and
        solver identifier. Keys are JSON-serialisable so telemetry exporters can persist them.
    warnings :
        Optional warnings accumulated across the rolling run; empty list when none are present.
    """

    locked_assignments: list[ScheduleLock]
    iteration_summaries: list[RollingIterationSummary]
    metadata: dict[str, object]
    warnings: list[str] | None = None


@dataclass
class RollingKPIComparison:
    """Comparison payload capturing rolling vs. baseline KPI metrics.

    Attributes
    ----------
    rolling_assignments :
        DataFrame version of ``RollingPlanResult.locked_assignments`` suitable for playback/KPI runs.
    rolling_kpis :
        KPI totals computed from the rolling plan assignments.
    baseline_assignments :
        Optional baseline schedule (full-horizon heuristic/MIP output) for comparison.
    baseline_kpis :
        KPI totals computed from ``baseline_assignments`` when provided.
    delta_totals :
        Numeric difference ``rolling - baseline`` for KPI keys present in both payloads.
    """

    rolling_assignments: pd.DataFrame
    rolling_kpis: KPIResult
    baseline_assignments: pd.DataFrame | None = None
    baseline_kpis: KPIResult | None = None
    delta_totals: dict[str, float] | None = None


@dataclass
class SolverOutput:
    """Return type for rolling-horizon solver hooks.

    Attributes
    ----------
    assignments :
        Sequence of :class:`fhops.scenario.contract.models.ScheduleLock` entries in
        sub-horizon coordinates (day 1 maps to the iteration start). Only the first
        ``RollingIterationPlan.lock_days`` will be frozen by the orchestrator.
    objective :
        Objective value reported by the solver or ``None`` when unavailable.
    runtime_s :
        Wall-clock runtime in seconds, when provided by the solver.
    warnings :
        Optional warnings emitted by the solver (solver status, termination condition, etc.).
    """

    assignments: Sequence[ScheduleLock]
    objective: float | None = None
    runtime_s: float | None = None
    warnings: list[str] | None = None


class IterableSolver(Protocol):
    """Protocol-like callable wrapper for solver hooks."""

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput: ...


class RollingInfeasibleError(RuntimeError):
    """Raised when a sub-horizon is infeasible or when solver configuration is invalid."""


def run_rolling_horizon(
    config: RollingHorizonConfig,
    solver: IterableSolver,
    *,
    max_iterations: int | None = None,
    solver_name: str | None = None,
) -> RollingPlanResult:
    """Execute the rolling-horizon loop with a user-supplied solver hook.

    The solver hook is responsible for producing assignments for each subproblem. This orchestrator
    handles window planning, scenario slicing, lock rebasing, and aggregation of locked decisions.
    Only the first ``lock_days`` of each iteration are frozen; the remainder of the sub-horizon is
    discarded when rolling forward.

    Parameters
    ----------
    config:
        Rolling-horizon configuration describing master/sub/lock horizons.
    solver:
        Callable that accepts a sliced scenario, the iteration plan, and the current locked
        assignments (rebased to the sub-horizon) and returns an iterable of ScheduleLock entries for
        that subproblem, plus optional metadata.
    max_iterations:
        Optional guard to cap the number of iterations (useful for smoke tests).
    solver_name:
        Optional solver label to persist into :class:`RollingPlanResult.metadata`.

    Returns
    -------
    RollingPlanResult
        Locked assignments in base-scenario coordinates plus per-iteration summaries.

    Raises
    ------
    RollingInfeasibleError
        If a sub-horizon is empty or violates basic feasibility checks before solving.
    """

    iteration_plans = build_iteration_plan(config)
    if max_iterations is not None:
        iteration_plans = iteration_plans[:max_iterations]

    locked_base: list[ScheduleLock] = []
    summaries: list[RollingIterationSummary] = []

    for plan in iteration_plans:
        sliced = slice_scenario_for_window(
            config.scenario,
            plan,
            locked_assignments=locked_base,
        )

        _assert_subproblem_feasible(sliced, plan)

        solver_output = solver(
            sliced,
            plan,
            locked_assignments=_rebase_locks(
                locked_base,
                plan.start_day,
                plan.end_day,
            )
            or [],
        )

        locked_portion = _lift_locks_to_base(
            solver_output.assignments, plan.start_day, plan.lock_days
        )
        locked_base.extend(locked_portion)

        summaries.append(
            RollingIterationSummary(
                iteration_index=plan.iteration_index,
                start_day=plan.start_day,
                horizon_days=plan.horizon_days,
                lock_days=plan.lock_days,
                locked_assignments=len(locked_portion),
                objective=solver_output.objective,
                runtime_s=solver_output.runtime_s,
                warnings=solver_output.warnings or None,
            )
        )

    metadata = {
        "scenario": config.scenario.name,
        "master_days": config.master_days,
        "subproblem_days": config.subproblem_days,
        "lock_days": config.lock_days,
        "start_day": config.start_day,
        "solver": solver_name or getattr(solver, "name", None),
    }
    solver_backend = getattr(solver, "solver", None)
    if solver_backend is not None:
        metadata["mip_solver"] = solver_backend
    solver_time_limit = getattr(solver, "time_limit", None)
    if solver_time_limit is not None:
        metadata["mip_time_limit"] = solver_time_limit
    solver_options = getattr(solver, "solver_options", None)
    if solver_options:
        metadata["mip_solver_options"] = dict(solver_options)

    return RollingPlanResult(
        locked_assignments=locked_base,
        iteration_summaries=summaries,
        metadata=metadata,
        warnings=[],
    )


def _lift_locks_to_base(
    locks: Iterable[ScheduleLock], start_day: int, lock_days: int
) -> list[ScheduleLock]:
    lifted: list[ScheduleLock] = []
    for lock in locks:
        if 1 <= lock.day <= lock_days:
            lifted.append(lock.model_copy(update={"day": start_day + lock.day - 1}, deep=True))
    return lifted


def _assert_subproblem_feasible(scenario: Scenario, plan: RollingIterationPlan) -> None:
    """Best-effort guard against empty or invalid subproblems before solving."""

    if not scenario.blocks:
        raise RollingInfeasibleError(
            f"Iteration {plan.iteration_index} ({plan.start_day}-{plan.end_day}) has no blocks"
        )
    if not scenario.production_rates:
        raise RollingInfeasibleError(
            f"Iteration {plan.iteration_index} ({plan.start_day}-{plan.end_day}) "
            "has no production rates"
        )
    machine_ids = {machine.id for machine in scenario.machines}
    if not machine_ids:
        raise RollingInfeasibleError(
            f"Iteration {plan.iteration_index} ({plan.start_day}-{plan.end_day}) has no machines"
        )

    # Ensure at least one calendar entry overlaps the sub-horizon.
    if scenario.calendar:
        window_has_supply = any(entry.machine_id in machine_ids for entry in scenario.calendar)
        if not window_has_supply:
            raise RollingInfeasibleError(
                f"Iteration {plan.iteration_index} ({plan.start_day}-{plan.end_day}) "
                "has no machine availability in calendar"
            )


class StubSolver:
    """Placeholder solver that returns no assignments.

    Notes
    -----
    This hook is useful for smoke tests of the rolling orchestrator/CLI. It always returns an empty
    assignment list and a warning noting that no work was performed.
    """

    name = "stub"

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput:
        warning = (
            f"[stub solver] iteration {plan.iteration_index} "
            f"({plan.start_day}-{plan.end_day}): no assignments produced"
        )
        return SolverOutput(assignments=[], objective=None, runtime_s=None, warnings=[warning])


class SASolver:
    """Rolling-horizon solver hook using the SA baseline.

    Parameters
    ----------
    iters :
        Number of simulated annealing iterations to execute per subproblem.
    seed :
        Random seed for deterministic neighbour selection and acceptance decisions.
    """

    name = "sa"

    def __init__(self, iters: int = 500, seed: int = 42) -> None:
        self.iters = iters
        self.seed = seed

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput:
        scenario.locked_assignments = list(locked_assignments or [])
        pb = Problem.from_scenario(scenario)

        result = solve_sa(pb, iters=self.iters, seed=self.seed)
        assignments = result.get("assignments")
        if assignments is None:
            return SolverOutput(assignments=[], objective=result.get("objective"), runtime_s=None)

        locks: list[ScheduleLock] = []
        for row in assignments.itertuples(index=False):
            assigned_value = getattr(row, "assigned", 1)
            if assigned_value:
                locks.append(
                    ScheduleLock(
                        machine_id=str(getattr(row, "machine_id")),
                        block_id=str(getattr(row, "block_id")),
                        day=int(getattr(row, "day")),
                    )
                )

        return SolverOutput(
            assignments=locks,
            objective=result.get("objective"),
            runtime_s=result.get("runtime_s"),
            warnings=result.get("warnings"),
        )


class MILPSolver:
    """Rolling-horizon solver hook using the operational MILP.

    Parameters
    ----------
    solver :
        Pyomo backend to invoke (e.g., ``\"highs\"``, ``\"gurobi\"``, or ``\"auto\"``).
    time_limit :
        Solve time limit in seconds for each subproblem.
    solver_options :
        Optional solver-specific options forwarded to Pyomo (e.g., ``{\"Threads\": 64}`` for Gurobi).
    """

    name = "mip"

    def __init__(
        self,
        solver: str = "auto",
        time_limit: int = 300,
        solver_options: Mapping[str, object] | None = None,
    ) -> None:
        self.solver = solver
        self.time_limit = time_limit
        self.solver_options = solver_options

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput:
        scenario.locked_assignments = list(locked_assignments or [])
        pb = Problem.from_scenario(scenario)
        ctx = build_operational_problem(pb)

        result = solve_operational_milp(
            ctx.bundle,
            solver=self.solver,
            time_limit=self.time_limit,
            solver_options=self.solver_options,
            context=ctx,
        )

        assignments_df = result.get("assignments")
        locks: list[ScheduleLock] = []
        if assignments_df is not None:
            for row in assignments_df.itertuples(index=False):
                locks.append(
                    ScheduleLock(
                        machine_id=str(getattr(row, "machine_id")),
                        block_id=str(getattr(row, "block_id")),
                        day=int(getattr(row, "day")),
                    )
                )

        warnings: list[str] = []
        solver_status = result.get("solver_status")
        if solver_status:
            warnings.append(f"solver_status={solver_status}")
        termination_condition = result.get("termination_condition")
        if termination_condition:
            warnings.append(f"termination_condition={termination_condition}")

        return SolverOutput(
            assignments=locks,
            objective=result.get("objective"),
            runtime_s=result.get("runtime_s"),
            warnings=warnings or None,
        )


def get_solver_hook(
    name: str,
    *,
    sa_iters: int = 500,
    sa_seed: int = 42,
    mip_solver: str = "auto",
    mip_time_limit: int = 300,
    mip_solver_options: Mapping[str, object] | None = None,
) -> IterableSolver:
    """Resolve a solver hook by name.

    Parameters
    ----------
    name :
        Solver identifier (``\"sa\"``, ``\"mip\"``/``\"milp\"``, or ``\"stub\"``).
    sa_iters :
        Number of iterations to run when ``name == "sa"``.
    sa_seed :
        Random seed passed to the SA hook for deterministic runs.
    mip_solver :
        Pyomo MILP driver to invoke when ``name`` is ``"mip"`` or ``"milp"``.
    mip_time_limit :
        Solve time limit in seconds for the MILP hook.
    mip_solver_options :
        Optional solver-specific parameters forwarded to the MILP backend (e.g., ``{\"Threads\": 64}``).

    Returns
    -------
    IterableSolver
        Callable that consumes a sliced scenario and iteration plan.

    Raises
    ------
    RollingInfeasibleError
        If an unsupported solver name is supplied.
    """

    if name.lower() == "stub":
        return StubSolver()
    if name.lower() == "sa":
        return SASolver(iters=sa_iters, seed=sa_seed)
    if name.lower() in {"mip", "milp"}:
        return MILPSolver(
            solver=mip_solver, time_limit=mip_time_limit, solver_options=mip_solver_options
        )
    raise RollingInfeasibleError(
        f"Unsupported solver '{name}'. Use 'sa', 'mip', or 'stub' until additional hooks land."
    )


def solve_rolling_plan(
    scenario: Scenario,
    *,
    master_days: int,
    subproblem_days: int,
    lock_days: int,
    solver: str = "sa",
    sa_iters: int = 500,
    sa_seed: int = 42,
    mip_solver: str = "auto",
    mip_time_limit: int = 300,
    mip_solver_options: Mapping[str, object] | None = None,
    max_iterations: int | None = None,
) -> RollingPlanResult:
    """Library-facing helper to execute a rolling-horizon plan.

    Parameters
    ----------
    scenario :
        Validated scenario to slice into rolling subproblems.
    master_days :
        Total number of days to lock in across the rolling run. Must satisfy
        ``master_days + start_day - 1 <= scenario.num_days``.
    subproblem_days :
        Number of days solved per iteration (≥ ``lock_days``).
    lock_days :
        Number of leading days to freeze after each iteration (≤ ``subproblem_days``).
    solver :
        Solver hook to use (``"sa"``, ``"mip"``, ``"milp"``, or ``"stub"``).
    sa_iters :
        Simulated annealing iteration budget when ``solver == "sa"``.
    sa_seed :
        Random seed for SA runs to keep results deterministic across iterations.
    mip_solver :
        Pyomo MILP driver name when ``solver`` is MILP-backed.
    mip_time_limit :
        Time limit in seconds for each MILP subproblem solve.
    mip_solver_options :
        Optional solver-specific parameters forwarded to the MILP backend (e.g., ``{\"Threads\": 64}``).
    max_iterations :
        Optional guard to cap the number of iterations (useful for smoke tests).

    Returns
    -------
    RollingPlanResult
        Locked assignments, per-iteration summaries, and metadata describing the run.

    Raises
    ------
    ValueError
        If horizon parameters violate basic bounds (e.g., master horizon exceeds scenario length).
    RollingInfeasibleError
        If the solver name is unsupported or a subproblem fails basic feasibility checks.
    """

    config = RollingHorizonConfig(
        scenario=scenario,
        master_days=master_days,
        subproblem_days=subproblem_days,
        lock_days=lock_days,
    )
    solver_hook = get_solver_hook(
        solver,
        sa_iters=sa_iters,
        sa_seed=sa_seed,
        mip_solver=mip_solver,
        mip_time_limit=mip_time_limit,
        mip_solver_options=mip_solver_options,
    )
    return run_rolling_horizon(
        config,
        solver_hook,
        max_iterations=max_iterations,
        solver_name=solver,
    )


def summarize_plan(result: RollingPlanResult) -> dict[str, object]:
    """Return a JSON-serialisable summary of a rolling-horizon run.

    Parameters
    ----------
    result:
        Rolling plan result with locked assignments and per-iteration summaries.

    Returns
    -------
    dict
        Dictionary containing iteration records, total locked assignments, and warnings. Suitable for
        emitting as JSON/CSV telemetry in CLI helpers.
    """

    iteration_records = [
        {
            "iteration_index": summary.iteration_index,
            "start_day": summary.start_day,
            "horizon_days": summary.horizon_days,
            "lock_days": summary.lock_days,
            "locked_assignments": summary.locked_assignments,
            "objective": summary.objective,
            "runtime_s": summary.runtime_s,
            "warnings": summary.warnings or [],
        }
        for summary in result.iteration_summaries
    ]

    return {
        "iterations": iteration_records,
        "total_locked_assignments": len(result.locked_assignments),
        "metadata": result.metadata,
        "warnings": result.warnings or [],
    }


def rolling_assignments_dataframe(
    result: RollingPlanResult,
    *,
    include_metadata: bool = False,
) -> pd.DataFrame:
    """Return locked assignments as a DataFrame for playback/KPI workflows.

    Parameters
    ----------
    result :
        Rolling plan output produced by :func:`run_rolling_horizon` or :func:`solve_rolling_plan`.
    include_metadata :
        When ``True`` append run metadata (scenario, horizons, solver label) to each row so exports
        remain self-describing.

    Returns
    -------
    pandas.DataFrame
        Columns include ``machine_id``, ``block_id``, ``day``, and optionally the metadata keys.

    Notes
    -----
    The resulting frame can be passed directly to :func:`fhops.evaluation.compute_kpis` or
    :func:`fhops.evaluation.playback.run_playback` to evaluate the rolling plan in the same way as a
    monolithic solve. Shift identifiers default to ``\"S1\"`` downstream when omitted.
    """

    metadata = result.metadata or {}
    meta_keys = [
        "scenario",
        "solver",
        "master_days",
        "subproblem_days",
        "lock_days",
        "start_day",
    ]
    rows: list[dict[str, object]] = []
    for lock in result.locked_assignments:
        row: dict[str, object] = {
            "machine_id": lock.machine_id,
            "block_id": lock.block_id,
            "day": lock.day,
        }
        if include_metadata:
            for key in meta_keys:
                if key in metadata:
                    row[key] = metadata[key]
        rows.append(row)

    columns = ["machine_id", "block_id", "day", "assigned"] + (
        meta_keys if include_metadata else []
    )
    if not rows:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame(rows)
    frame["assigned"] = 1
    return (
        frame.reindex(columns=columns, fill_value=None)
        .sort_values(["day", "machine_id", "block_id"])
        .reset_index(drop=True)
    )


def compute_rolling_kpis(
    scenario: Scenario | Problem,
    result: RollingPlanResult | pd.DataFrame | Sequence[ScheduleLock],
    *,
    baseline_assignments: pd.DataFrame | Sequence[ScheduleLock] | None = None,
) -> RollingKPIComparison:
    """Compute KPI totals for a rolling plan and compare them to an optional baseline.

    Parameters
    ----------
    scenario :
        Scenario or :class:`fhops.scenario.contract.Problem` describing the planning horizon. The
        helper converts it to a :class:`Problem` for KPI evaluation when necessary.
    result :
        Rolling plan output returned by :func:`solve_rolling_plan`, or a DataFrame/``ScheduleLock``
        sequence of locked assignments exported by the CLI (columns: ``machine_id``, ``block_id``,
        ``day`` and optional ``shift_id``).
    baseline_assignments :
        Optional baseline schedule (full-horizon MILP/SA run) supplied as a Pandas DataFrame or
        sequence of :class:`fhops.scenario.contract.models.ScheduleLock` rows. Required columns
        mirror the rolling assignments (``machine_id``, ``block_id``, ``day`` and optional
        ``shift_id``). When omitted, delta fields remain ``None``.

    Returns
    -------
    RollingKPIComparison
        Bundle containing ``rolling_assignments`` (DataFrame), ``rolling_kpis`` and
        ``baseline_kpis`` (when provided), and ``delta_totals`` containing ``<metric>_delta`` and
        ``<metric>_pct_delta`` entries for numeric KPIs.

    Raises
    ------
    ValueError
        If the rolling plan does not contain any locked assignments.
    TypeError
        If ``baseline_assignments`` is not a DataFrame or sequence of ``ScheduleLock`` entries.

    Examples
    --------
    >>> from fhops.planning import solve_rolling_plan, compute_rolling_kpis
    >>> scenario = load_scenario(\"examples/tiny7/scenario.yaml\")
    >>> rolling = solve_rolling_plan(scenario, master_days=7, subproblem_days=7, lock_days=7)
    >>> comparison = compute_rolling_kpis(scenario, rolling)
    >>> comparison.rolling_kpis[\"total_production\"]
    5000.0  # example value
    """

    baseline_df = _normalize_assignments_input(baseline_assignments)
    rolling_assignments: pd.DataFrame | None
    if isinstance(result, RollingPlanResult):
        if not result.locked_assignments:
            raise ValueError("Rolling plan contains no locked assignments; cannot compute KPIs.")
        rolling_assignments = rolling_assignments_dataframe(result, include_metadata=False)
    else:
        rolling_assignments = _normalize_assignments_input(result)

    if rolling_assignments is None:
        raise ValueError("Rolling plan contains no locked assignments; cannot compute KPIs.")

    problem = scenario if isinstance(scenario, Problem) else Problem.from_scenario(scenario)
    rolling_kpis = compute_kpis(problem, rolling_assignments)
    baseline_kpis: KPIResult | None = None
    if baseline_df is not None:
        baseline_kpis = compute_kpis(problem, baseline_df)

    delta_totals = None
    if baseline_kpis is not None:
        delta_totals = _compute_kpi_deltas(rolling_kpis, baseline_kpis)

    return RollingKPIComparison(
        rolling_assignments=rolling_assignments,
        rolling_kpis=rolling_kpis,
        baseline_assignments=baseline_df,
        baseline_kpis=baseline_kpis,
        delta_totals=delta_totals,
    )


def _compute_kpi_deltas(current: KPIResult, baseline: KPIResult) -> dict[str, float]:
    current_numeric = _numeric_totals(current)
    baseline_numeric = _numeric_totals(baseline)
    shared_keys = current_numeric.keys() & baseline_numeric.keys()
    deltas: dict[str, float] = {}
    for key in sorted(shared_keys):
        current_value = current_numeric[key]
        baseline_value = baseline_numeric[key]
        delta = current_value - baseline_value
        deltas[f"{key}_delta"] = delta
        if baseline_value != 0:
            deltas[f"{key}_pct_delta"] = delta / baseline_value
    return deltas


def _numeric_totals(kpi: KPIResult) -> dict[str, float]:
    totals: dict[str, float] = {}
    for key, value in kpi.to_dict().items():
        if isinstance(value, Number):
            totals[key] = float(value)
    return totals


def _normalize_assignments_input(
    assignments: pd.DataFrame | Sequence[ScheduleLock] | None,
) -> pd.DataFrame | None:
    """Return a DataFrame representation of assignments or ``None`` when empty."""

    if assignments is None:
        return None
    if isinstance(assignments, pd.DataFrame):
        if assignments.empty:
            return None
        missing = {"machine_id", "block_id", "day"} - set(assignments.columns)
        if missing:
            raise ValueError(
                "assignments dataframe missing required columns: " + ", ".join(sorted(missing))
            )
        return assignments.copy()
    if isinstance(assignments, Sequence):
        locks = list(assignments)
        if not locks:
            return None
        if not all(isinstance(lock, ScheduleLock) for lock in locks):
            raise TypeError(
                "Sequence baseline input must contain fhops.scenario.contract.ScheduleLock entries"
            )
        return rolling_assignments_dataframe(
            RollingPlanResult(
                locked_assignments=list(locks),
                iteration_summaries=[],
                metadata={},
            ),
            include_metadata=False,
        )
    raise TypeError(
        "assignments input must be a pandas.DataFrame or a sequence of ScheduleLock entries"
    )
