"""Rolling-horizon replanning utilities.

This module provides the core planning primitives for building multi-iteration schedules: slicing a
scenario into sub-horizons, tracking locked-in assignments, and constructing iteration plans that
advance the window by a configurable lock span. Solver integration (heuristics/MILP) attaches to
these primitives so both CLI and Python callers share the same orchestration layer.

State carry-forward (FHOPS 1.0.1, #92)
--------------------------------------
After each iteration locks its leading days, the stitched locked plan is replayed against the
**base** scenario with the deterministic playback sequencing tracker
(:func:`fhops.evaluation.playback.assignments_to_records`, rate-based production capped by the
tracker; the same rule :func:`compute_rolling_kpis` uses). The tracker state at the next window
start becomes the next window's boundary condition (see :func:`carry_forward_state`):

- ``Block.work_required`` = remaining terminal volume (finished blocks stay with ``0``);
- ``Scenario.initial_state`` = per-block ``role_remaining`` / ``staged_inventory`` /
  ``role_shift_counts`` and per-machine ``last_block_id``.

The replay starts from the base scenario's own ``initial_state`` (when supplied), so user-supplied
state and the stitched plan compose. User ``Scenario.locked_assignments`` are rebased into every
window they fall in, and solver hooks merge (never overwrite) the locks they receive.

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

import time
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from numbers import Number
from typing import Protocol

import pandas as pd

from fhops.evaluation import KPIResult, compute_kpis
from fhops.evaluation.playback import assignments_to_records
from fhops.evaluation.sequencing import (
    BLOCK_EPSILON,
    SequencingTracker,
    build_sequencing_tracker,
)
from fhops.model.milp.driver import solve_operational_milp
from fhops.optimization.heuristics.sa import solve_sa
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import (
    Block,
    BlockInitialState,
    CalendarEntry,
    MachineInitialState,
    Scenario,
    ScenarioInitialState,
    ScheduleLock,
    ShiftCalendarEntry,
)
from fhops.scheduling.mobilisation.models import BlockDistance, MobilisationConfig
from fhops.scheduling.timeline.models import BlackoutWindow, TimelineConfig

#: Operational MILP backend used when a rolling MILP hook is configured with ``solver="auto"``
#: (matches the ``fhops solve-mip-operational`` default).
DEFAULT_OPERATIONAL_MIP_SOLVER = "highs"

#: Playback fills missing shift labels with this value (see
#: :func:`fhops.evaluation.playback.assignments_to_records`).
_DEFAULT_SHIFT_ID = "S1"

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
    "RollingCarryState",
    "carry_forward_state",
    "rolling_assignments_dataframe",
    "compute_rolling_kpis",
    "DEFAULT_OPERATIONAL_MIP_SOLVER",
    "resolve_operational_mip_solver",
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


@dataclass
class RollingCarryState:
    """Boundary state carried into a rolling-horizon window (FHOPS 1.0.1, #92).

    Produced by :func:`carry_forward_state` from a deterministic replay of the stitched locked plan
    against the base scenario, and consumed by :func:`slice_scenario_for_window`.

    Attributes
    ----------
    through_day :
        Last base-scenario day (inclusive) covered by the replay; the next window starts at
        ``through_day + 1``.
    remaining_work :
        ``block_id -> m³`` terminal volume still to deliver after ``through_day`` (the sequencing
        tracker's ``remaining_work``; values ``<= 1e-6`` are reported as ``0.0``). Every base block
        is present; finished blocks map to ``0.0``. The slicer uses it as the window's
        ``Block.work_required``.
    initial_state :
        :class:`fhops.scenario.contract.ScenarioInitialState` for the next window, or ``None`` when
        every entry is at its default. Per explicit-system block it lists ``role_remaining``
        (omitted when equal to the block's remaining terminal volume, the contract default),
        ``staged_inventory`` (omitted when zero, and for terminal roles, whose output is delivered
        volume rather than staged input) and ``role_shift_counts`` (omitted when zero); per
        machine it lists ``last_block_id`` (the block of the machine's last locked assignment,
        ordered by ``(day, shift_id)``, falling back to the base ``initial_state``).
    """

    through_day: int
    remaining_work: dict[str, float]
    initial_state: ScenarioInitialState | None = None


def carry_forward_state(
    base: Scenario,
    locked_assignments: Sequence[ScheduleLock],
    *,
    through_day: int,
) -> RollingCarryState:
    """Replay a stitched locked plan on the base scenario and return the carried-forward state.

    Parameters
    ----------
    base :
        Base (unsliced) scenario. Its ``initial_state`` (when set) seeds the replay, so carried
        state composes with user-supplied state. Not mutated.
    locked_assignments :
        Stitched locked plan in base-scenario coordinates (e.g.
        :attr:`RollingPlanResult.locked_assignments`). Entries with ``day > through_day`` are
        ignored. ``shift_id`` is honoured; ``None`` is replayed as ``"S1"`` exactly like playback.
    through_day :
        Last base day (inclusive) to replay. Must be ``>= 0``.

    Returns
    -------
    RollingCarryState
        Remaining terminal volume per block plus the per-block/per-machine initial state for a
        window starting at ``through_day + 1``.

    Notes
    -----
    Production follows the deterministic playback rule: each assignment proposes
    ``min(rate, block remaining)`` and the shared
    :class:`fhops.evaluation.sequencing.SequencingTracker` caps it by the role's remaining output
    and the staged upstream inventory. Solver-planned production (e.g. the MILP ``prod`` values) is
    **not** used, so the carried state is exactly the state :func:`compute_rolling_kpis` /
    :func:`fhops.evaluation.compute_kpis` report for the same locked plan. Role-keyed state is only
    emitted for blocks with an explicit ``harvest_system_id`` and for roles of that system
    (matching :func:`fhops.scenario.contract.validate_initial_state`).
    """

    if through_day < 0:
        raise ValueError("through_day must be >= 0")
    locks = [lock for lock in locked_assignments if lock.day <= through_day]
    problem = Problem.from_scenario(base)
    tracker = _replay_tracker(problem, locks)
    ctx = tracker.ctx

    remaining_work: dict[str, float] = {}
    for block in base.blocks:
        value = float(tracker.remaining_work.get(block.id, block.work_required))
        remaining_work[block.id] = 0.0 if value <= BLOCK_EPSILON else value

    block_states: list[BlockInitialState] = []
    for block in base.blocks:
        block_id = block.id
        if block_id not in ctx.blocks_with_explicit_system:
            continue
        system_id = ctx.bundle.block_system.get(block_id)
        system = ctx.bundle.systems.get(system_id) if system_id else None
        if system is None:
            continue
        system_roles = [cfg.role for cfg in system.roles if cfg.role]
        terminal = ctx.terminal_roles.get(system.system_id, frozenset())
        role_remaining: dict[str, float] = {}
        staged: dict[str, float] = {}
        counts: dict[str, int] = {}
        for role in system_roles:
            key = (block_id, role)
            if key in tracker.role_remaining:
                value = float(tracker.role_remaining[key])
                value = 0.0 if value <= BLOCK_EPSILON else value
                if abs(value - remaining_work[block_id]) > 1e-9:
                    role_remaining[role] = value
            inventory = float(tracker.role_inventory.get(key, 0.0))
            if role not in terminal and inventory > BLOCK_EPSILON:
                staged[role] = inventory
            count = int(tracker.role_counts_total.get(key, 0))
            if count > 0:
                counts[role] = count
        if role_remaining or staged or counts:
            block_states.append(
                BlockInitialState(
                    block_id=block_id,
                    role_remaining=role_remaining,
                    staged_inventory=staged,
                    role_shift_counts=counts,
                )
            )

    last_block: dict[str, str] = (
        dict(base.initial_state.last_block_by_machine()) if base.initial_state else {}
    )
    for lock in sorted(locks, key=lambda item: (item.day, item.shift_id or _DEFAULT_SHIFT_ID)):
        last_block[lock.machine_id] = lock.block_id
    machine_states = [
        MachineInitialState(machine_id=machine.id, last_block_id=last_block[machine.id])
        for machine in base.machines
        if machine.id in last_block
    ]

    initial_state = None
    if block_states or machine_states:
        initial_state = ScenarioInitialState(blocks=block_states, machines=machine_states)
    return RollingCarryState(
        through_day=through_day,
        remaining_work=remaining_work,
        initial_state=initial_state,
    )


def _replay_tracker(problem: Problem, locks: Sequence[ScheduleLock]) -> SequencingTracker:
    """Replay ``locks`` through deterministic playback and return the finalised tracker."""

    frame = _locks_frame(locks)
    if frame.empty:
        return build_sequencing_tracker(problem)
    records = assignments_to_records(problem, frame)
    for _ in records:
        pass
    tracker = getattr(records, "sequencing_tracker", None)
    if tracker is None:  # pragma: no cover - defensive (empty frames handled above)
        return build_sequencing_tracker(problem)
    tracker.finalize()
    return tracker


def _locks_frame(locks: Iterable[ScheduleLock]) -> pd.DataFrame:
    """Return ``machine_id, block_id, day, shift_id, assigned`` rows for ``locks``."""

    rows = [
        {
            "machine_id": lock.machine_id,
            "block_id": lock.block_id,
            "day": lock.day,
            "shift_id": lock.shift_id,
            "assigned": 1,
        }
        for lock in locks
    ]
    return pd.DataFrame(rows, columns=["machine_id", "block_id", "day", "shift_id", "assigned"])


def slice_scenario_for_window(
    base: Scenario,
    window: RollingIterationPlan,
    locked_assignments: Sequence[ScheduleLock] | None = None,
    *,
    carry_state: RollingCarryState | None = None,
) -> Scenario:
    """Return a horizon-trimmed scenario for the given iteration window.

    The slice rebases day indices so the window start maps to day 1: machine and shift calendars,
    timeline blackouts, block windows, and locks outside the window are dropped and the rest are
    shifted. Blocks whose ``[earliest_start, latest_finish]`` window does not overlap the
    sub-horizon are dropped together with their production rates and mobilisation distances.

    Parameters
    ----------
    base:
        Original scenario to slice. This object is not mutated.
    window:
        Iteration window describing the start day and sub-horizon length.
    locked_assignments:
        Optional extra locks (base-scenario coordinates) **merged** with ``base.locked_assignments``
        (FHOPS <= 1.0.0 replaced the scenario's locks instead). Exact duplicates are collapsed;
        conflicting locks are rejected by :class:`Scenario` validation. Only locks inside the window
        are retained (day-rebased, ``shift_id`` preserved).
    carry_state:
        Optional :class:`RollingCarryState` (see :func:`carry_forward_state`). When given, each
        block's ``work_required`` is set to ``carry_state.remaining_work`` (finished blocks stay
        with ``0``) and ``initial_state`` is set to ``carry_state.initial_state``. When omitted, the
        base ``work_required`` and ``initial_state`` are kept (window 0 / direct-solve behaviour).

    Returns
    -------
    Scenario
        A re-validated deep copy with ``num_days == window.horizon_days``. Initial-state entries for
        dropped blocks are removed, as are ``last_block_id`` values that point at dropped blocks
        (a ``UserWarning`` is emitted for the latter because the boundary move is then free in the
        window solve).

    Raises
    ------
    RollingInfeasibleError
        If a lock inside the window references a block that is outside the window.
    ValueError
        (Pydantic ``ValidationError``) if the merged locks conflict.
    """

    sliced, messages = _slice_window(
        base, window, locked_assignments=locked_assignments, carry_state=carry_state
    )
    for message in messages:
        warnings.warn(message, UserWarning, stacklevel=2)
    return sliced


def _slice_window(
    base: Scenario,
    window: RollingIterationPlan,
    *,
    locked_assignments: Sequence[ScheduleLock] | None = None,
    carry_state: RollingCarryState | None = None,
) -> tuple[Scenario, list[str]]:
    start = window.start_day
    end = window.end_day
    messages: list[str] = []
    copy = base.model_copy(deep=True)
    updates: dict[str, object] = {"num_days": window.horizon_days}

    if copy.start_date:
        updates["start_date"] = copy.start_date + timedelta(days=start - 1)

    updates["calendar"] = _rebase_calendar(copy.calendar, start, end)
    updates["shift_calendar"] = _rebase_shift_calendar(copy.shift_calendar, start, end)
    updates["timeline"] = _rebase_timeline(copy.timeline, start, end)

    remaining = carry_state.remaining_work if carry_state is not None else None
    filtered_blocks, kept_blocks = _filter_and_rebase_blocks(
        base, start, end, window.horizon_days, remaining
    )
    updates["blocks"] = filtered_blocks
    updates["production_rates"] = [
        rate for rate in copy.production_rates if rate.block_id in kept_blocks
    ]
    updates["mobilisation"] = _filter_mobilisation(copy.mobilisation, kept_blocks)

    merged_locks = _merge_locks(copy.locked_assignments or [], locked_assignments or [])
    window_locks = _rebase_locks(merged_locks, start, end) or []
    for lock in window_locks:
        if lock.block_id not in kept_blocks:
            raise RollingInfeasibleError(
                f"Iteration {window.iteration_index} ({start}-{end}): locked assignment "
                f"{lock.machine_id}->{lock.block_id} on base day {lock.day + start - 1} targets a "
                "block whose earliest_start/latest_finish window does not overlap this window"
            )
    if window_locks:
        updates["locked_assignments"] = window_locks
    else:
        updates["locked_assignments"] = None if copy.locked_assignments is None else []

    state = carry_state.initial_state if carry_state is not None else copy.initial_state
    updates["initial_state"] = _filter_initial_state(state, kept_blocks, window, messages)

    payload = {name: getattr(copy, name) for name in Scenario.model_fields}
    payload.update(updates)
    return Scenario.model_validate(payload), messages


def _merge_locks(*groups: Sequence[ScheduleLock]) -> list[ScheduleLock]:
    """Concatenate lock groups in order, dropping exact duplicates."""

    merged: list[ScheduleLock] = []
    seen: set[tuple[str, str, int, str | None]] = set()
    for group in groups:
        for lock in group:
            key = (lock.machine_id, lock.block_id, lock.day, lock.shift_id)
            if key in seen:
                continue
            seen.add(key)
            merged.append(lock)
    return merged


def _filter_initial_state(
    state: ScenarioInitialState | None,
    kept_blocks: set[str],
    window: RollingIterationPlan,
    messages: list[str],
) -> ScenarioInitialState | None:
    if state is None:
        return None
    blocks = [entry for entry in state.blocks if entry.block_id in kept_blocks]
    machines: list[MachineInitialState] = []
    for entry in state.machines:
        if entry.last_block_id is not None and entry.last_block_id not in kept_blocks:
            messages.append(
                f"Iteration {window.iteration_index} ({window.start_day}-{window.end_day}): "
                f"machine {entry.machine_id} last worked block {entry.last_block_id}, which is "
                "outside this window; its boundary move is not charged in the window solve"
            )
            continue
        machines.append(entry)
    if blocks == list(state.blocks) and machines == list(state.machines):
        return state
    if not blocks and not machines:
        return None
    return state.model_copy(update={"blocks": blocks, "machines": machines})


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


def _rebase_timeline(
    timeline: TimelineConfig | None, start: int, end: int
) -> TimelineConfig | None:
    """Clip blackout windows to ``[start, end]`` and shift them so ``start`` maps to day 1."""

    if timeline is None or not timeline.blackouts:
        return timeline
    rebased: list[BlackoutWindow] = []
    for blackout in timeline.blackouts:
        first = max(blackout.start_day, start)
        last = min(blackout.end_day, end)
        if first > last:
            continue
        rebased.append(
            blackout.model_copy(
                update={"start_day": first - start + 1, "end_day": last - start + 1}
            )
        )
    return timeline.model_copy(update={"blackouts": rebased})


def _filter_and_rebase_blocks(
    base: Scenario,
    start: int,
    end: int,
    horizon_days: int,
    remaining_work: Mapping[str, float] | None = None,
) -> tuple[list[Block], set[str]]:
    filtered_blocks: list[Block] = []
    kept_ids: set[str] = set()
    for block in base.blocks:
        earliest = block.earliest_start if block.earliest_start is not None else 1
        latest = block.latest_finish if block.latest_finish is not None else base.num_days

        if latest < start or earliest > end:
            continue

        update: dict[str, object] = {
            "earliest_start": max(1, earliest - (start - 1)),
            "latest_finish": min(horizon_days, latest - (start - 1)),
        }
        if remaining_work is not None:
            update["work_required"] = float(remaining_work.get(block.id, block.work_required))
        rebased = block.model_copy(deep=True, update=update)
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
    remaining_work_start :
        Terminal volume (m³) still to deliver across all base blocks at the start of this window,
        from the carried-forward state (the base ``work_required`` total for the first window).
        ``None`` when not computed (e.g. summaries built by hand).
    """

    iteration_index: int
    start_day: int
    horizon_days: int
    lock_days: int
    locked_assignments: int
    objective: float | None = None
    runtime_s: float | None = None
    warnings: list[str] | None = None
    remaining_work_start: float | None = None


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
    handles window planning, scenario slicing, lock rebasing, state carry-forward, and aggregation of
    locked decisions. Only the first ``lock_days`` of each iteration are frozen; the remainder of the
    sub-horizon is discarded when rolling forward.

    Before every iteration after the first, the stitched locked plan is replayed on the base
    scenario through day ``start_day - 1`` (:func:`carry_forward_state`), and the window is sliced
    with the resulting remaining volumes and ``initial_state`` (:func:`slice_scenario_for_window`).
    The first window uses the base ``work_required`` and ``initial_state`` unchanged, so a
    single-window run (``subproblem_days == lock_days == master_days``) is a direct solve.

    Parameters
    ----------
    config:
        Rolling-horizon configuration describing master/sub/lock horizons.
    solver:
        Callable that accepts a sliced scenario, the iteration plan, and the window's locks
        (``locked_assignments=``: the base scenario's user locks that fall in the window, rebased to
        window days; identical to ``scenario.locked_assignments``) and returns a
        :class:`SolverOutput` whose ``assignments`` are window-day :class:`ScheduleLock` entries.
        Hooks should set ``ScheduleLock.shift_id`` on multi-shift scenarios; entries without it are
        replayed as shift ``"S1"`` by playback.
    max_iterations:
        Optional guard to cap the number of iterations (useful for smoke tests).
    solver_name:
        Optional solver label to persist into :class:`RollingPlanResult.metadata`.

    Returns
    -------
    RollingPlanResult
        Locked assignments in base-scenario coordinates (``shift_id`` preserved) plus
        per-iteration summaries. ``warnings`` lists slicer notices (e.g. a carried
        ``last_block_id`` that falls outside a window).

    Raises
    ------
    RollingInfeasibleError
        If a sub-horizon is empty, violates basic feasibility checks before solving, or a user lock
        targets a block outside the window.
    """

    iteration_plans = build_iteration_plan(config)
    if max_iterations is not None:
        iteration_plans = iteration_plans[:max_iterations]

    base = config.scenario
    locked_base: list[ScheduleLock] = []
    summaries: list[RollingIterationSummary] = []
    run_warnings: list[str] = []

    for plan in iteration_plans:
        carry_state: RollingCarryState | None = None
        if plan.iteration_index > 0:
            carry_state = carry_forward_state(base, locked_base, through_day=plan.start_day - 1)
        sliced, slice_messages = _slice_window(base, plan, carry_state=carry_state)
        run_warnings.extend(slice_messages)

        _assert_subproblem_feasible(sliced, plan)

        solver_output = solver(
            sliced,
            plan,
            locked_assignments=list(sliced.locked_assignments or []),
        )

        locked_portion = _lift_locks_to_base(
            solver_output.assignments, plan.start_day, plan.lock_days
        )
        locked_base.extend(locked_portion)

        remaining_start = (
            sum(carry_state.remaining_work.values())
            if carry_state is not None
            else sum(block.work_required for block in base.blocks)
        )
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
                remaining_work_start=float(remaining_start),
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
        warnings=run_warnings,
    )


def _lift_locks_to_base(
    locks: Iterable[ScheduleLock], start_day: int, lock_days: int
) -> list[ScheduleLock]:
    """Lift window locks ``1..lock_days`` to base days, keeping ``shift_id``; drop exact repeats."""

    lifted: list[ScheduleLock] = []
    seen: set[tuple[str, str, int, str | None]] = set()
    for lock in locks:
        if 1 <= lock.day <= lock_days:
            base_day = start_day + lock.day - 1
            key = (lock.machine_id, lock.block_id, base_day, lock.shift_id)
            if key in seen:
                continue
            seen.add(key)
            lifted.append(lock.model_copy(update={"day": base_day}, deep=True))
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


def _scenario_with_locks(scenario: Scenario, locks: Sequence[ScheduleLock]) -> Scenario:
    """Return ``scenario`` with ``locks`` merged into its own locks (re-validated, not mutated)."""

    if not locks:
        return scenario
    merged = _merge_locks(scenario.locked_assignments or [], locks)
    if len(merged) == len(scenario.locked_assignments or []):
        return scenario
    payload = {name: getattr(scenario, name) for name in Scenario.model_fields}
    payload["locked_assignments"] = merged
    return Scenario.model_validate(payload)


def _assignment_rows_to_locks(assignments: pd.DataFrame | None) -> list[ScheduleLock]:
    """Convert solver assignment rows (``assigned > 0``) into shift-aware locks."""

    locks: list[ScheduleLock] = []
    if assignments is None or assignments.empty:
        return locks
    has_assigned = "assigned" in assignments.columns
    has_shift = "shift_id" in assignments.columns
    for row in assignments.itertuples(index=False):
        if has_assigned:
            assigned_value = getattr(row, "assigned")
            if pd.isna(assigned_value) or float(assigned_value) <= 0.5:
                continue
        shift_value = getattr(row, "shift_id") if has_shift else None
        shift_id = None if shift_value is None or pd.isna(shift_value) else str(shift_value)
        locks.append(
            ScheduleLock(
                machine_id=str(getattr(row, "machine_id")),
                block_id=str(getattr(row, "block_id")),
                day=int(getattr(row, "day")),
                shift_id=shift_id,
            )
        )
    return locks


def resolve_operational_mip_solver(solver: str | None) -> str:
    """Resolve the rolling MILP backend name (``"auto"``/``"default"``/empty → ``"highs"``).

    Parameters
    ----------
    solver :
        Requested backend name (case-insensitive). Any other value is passed through to
        ``pyomo.opt.SolverFactory`` unchanged (lower-cased and stripped).

    Returns
    -------
    str
        Concrete solver name; :data:`DEFAULT_OPERATIONAL_MIP_SOLVER` for automatic selection,
        matching the ``fhops solve-mip-operational`` default.
    """

    cleaned = (solver or "").strip().lower()
    if cleaned in {"", "auto", "default"}:
        return DEFAULT_OPERATIONAL_MIP_SOLVER
    return cleaned


class SASolver:
    """Rolling-horizon solver hook using the SA baseline.

    Parameters
    ----------
    iters :
        Number of simulated annealing iterations to execute per subproblem.
    seed :
        Random seed for deterministic neighbour selection and acceptance decisions.

    Notes
    -----
    The hook merges the ``locked_assignments`` it receives with ``scenario.locked_assignments``
    (exact duplicates collapsed; the scenario is not mutated), returns one shift-aware
    :class:`ScheduleLock` per worked ``(machine, day, shift)`` slot, and records the wall-clock
    runtime of the solve in ``SolverOutput.runtime_s``.
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
        start = time.perf_counter()
        pb = Problem.from_scenario(_scenario_with_locks(scenario, locked_assignments))
        result = solve_sa(pb, iters=self.iters, seed=self.seed)
        runtime = time.perf_counter() - start
        locks = _assignment_rows_to_locks(result.get("assignments"))
        return SolverOutput(
            assignments=locks,
            objective=result.get("objective"),
            runtime_s=runtime,
            warnings=result.get("warnings"),
        )


class MILPSolver:
    """Rolling-horizon solver hook using the operational MILP.

    Parameters
    ----------
    solver :
        Pyomo backend to invoke (e.g., ``\"highs\"``, ``\"gurobi\"``). ``\"auto\"`` (default)
        resolves to ``\"highs\"`` (:func:`resolve_operational_mip_solver`); the resolved name is
        stored in :attr:`solver` and reported as ``mip_solver`` in the run metadata.
    time_limit :
        Solve time limit in seconds for each subproblem.
    solver_options :
        Optional solver-specific options forwarded to Pyomo (e.g., ``{\"Threads\": 64}`` for Gurobi).

    Notes
    -----
    The hook merges the ``locked_assignments`` it receives with ``scenario.locked_assignments``
    (the operational MILP enforces them as equality constraints), keeps only rows with
    ``assigned = 1``, preserves ``shift_id``, and records the wall-clock runtime of model build +
    solve in ``SolverOutput.runtime_s``. Solver status and termination condition are reported as
    warnings.
    """

    name = "mip"

    def __init__(
        self,
        solver: str = "auto",
        time_limit: int = 300,
        solver_options: Mapping[str, object] | None = None,
    ) -> None:
        self.requested_solver = solver
        self.solver = resolve_operational_mip_solver(solver)
        self.time_limit = time_limit
        self.solver_options = solver_options

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput:
        start = time.perf_counter()
        pb = Problem.from_scenario(_scenario_with_locks(scenario, locked_assignments))
        ctx = build_operational_problem(pb)

        result = solve_operational_milp(
            ctx.bundle,
            solver=self.solver,
            time_limit=self.time_limit,
            solver_options=self.solver_options,
            context=ctx,
        )
        runtime = time.perf_counter() - start

        locks = _assignment_rows_to_locks(result.get("assignments"))

        messages: list[str] = []
        solver_status = result.get("solver_status")
        if solver_status:
            messages.append(f"solver_status={solver_status}")
        termination_condition = result.get("termination_condition")
        if termination_condition:
            messages.append(f"termination_condition={termination_condition}")

        return SolverOutput(
            assignments=locks,
            objective=result.get("objective"),
            runtime_s=runtime,
            warnings=messages or None,
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
        Pyomo MILP driver to invoke when ``name`` is ``"mip"`` or ``"milp"``; ``"auto"`` resolves
        to ``"highs"``.
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
        Pyomo MILP driver name when ``solver`` is MILP-backed; ``"auto"`` resolves to ``"highs"``.
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
            "remaining_work_start": summary.remaining_work_start,
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
        Columns ``machine_id``, ``block_id``, ``day``, ``shift_id``, ``assigned`` (always ``1``),
        and optionally the metadata keys, sorted by ``day``, ``shift_id``, ``machine_id``,
        ``block_id``. ``shift_id`` is ``None`` for day-level locks.

    Notes
    -----
    The resulting frame can be passed directly to :func:`fhops.evaluation.compute_kpis` or
    :func:`fhops.evaluation.playback.run_playback` to evaluate the rolling plan in the same way as a
    monolithic solve. Playback treats a missing ``shift_id`` as ``\"S1\"``. Evaluating the frame
    against the base scenario reproduces exactly the state carried between windows (see
    :func:`carry_forward_state`).
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
            "shift_id": lock.shift_id,
        }
        if include_metadata:
            for key in meta_keys:
                if key in metadata:
                    row[key] = metadata[key]
        rows.append(row)

    columns = ["machine_id", "block_id", "day", "shift_id", "assigned"] + (
        meta_keys if include_metadata else []
    )
    if not rows:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame(rows)
    frame["assigned"] = 1
    return (
        frame.reindex(columns=columns, fill_value=None)
        .sort_values(["day", "shift_id", "machine_id", "block_id"], na_position="first")
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
