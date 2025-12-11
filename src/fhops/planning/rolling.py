"""Rolling-horizon replanning utilities.

This module provides the core planning primitives for building multi-iteration schedules: slicing a
scenario into sub-horizons, tracking locked-in assignments, and constructing iteration plans that
advance the window by a configurable lock span. Solver integration (heuristics/MILP) will attach to
these primitives so both CLI and Python callers share the same orchestration layer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from fhops.optimization.heuristics.sa import solve_sa
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
    "RollingInfeasibleError",
    "StubSolver",
    "SASolver",
    "solve_rolling_plan",
    "get_solver_hook",
    "SolverOutput",
    "run_rolling_horizon",
    "summarize_plan",
    "build_iteration_plan",
    "slice_scenario_for_window",
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
    """Outcome summary for a single rolling-horizon iteration."""

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
    """Aggregated result for a rolling-horizon run."""

    locked_assignments: list[ScheduleLock]
    iteration_summaries: list[RollingIterationSummary]
    warnings: list[str] | None = None


@dataclass
class SolverOutput:
    """Return type for rolling-horizon solver hooks."""

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
    """Raised when a sub-horizon is infeasible or empty before solving."""


def run_rolling_horizon(
    config: RollingHorizonConfig,
    solver: IterableSolver,
    *,
    max_iterations: int | None = None,
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

    Returns
    -------
    RollingPlanResult
        Locked assignments in base-scenario coordinates plus per-iteration summaries.
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

    return RollingPlanResult(
        locked_assignments=locked_base,
        iteration_summaries=summaries,
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
    """Placeholder solver that returns no assignments."""

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
    """Rolling-horizon solver hook using the SA baseline."""

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


def get_solver_hook(name: str, *, sa_iters: int = 500, sa_seed: int = 42) -> IterableSolver:
    """Resolve a solver hook by name."""

    if name.lower() == "stub":
        return StubSolver()
    if name.lower() == "sa":
        return SASolver(iters=sa_iters, seed=sa_seed)
    raise RollingInfeasibleError(
        f"Unsupported solver '{name}'. Use 'sa' or 'stub' until additional hooks land."
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
) -> RollingPlanResult:
    """Library-facing helper to execute a rolling-horizon plan."""

    config = RollingHorizonConfig(
        scenario=scenario,
        master_days=master_days,
        subproblem_days=subproblem_days,
        lock_days=lock_days,
    )
    solver_hook = get_solver_hook(solver, sa_iters=sa_iters, sa_seed=sa_seed)
    return run_rolling_horizon(config, solver_hook)


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
        "warnings": result.warnings or [],
    }
