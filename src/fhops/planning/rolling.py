"""Rolling-horizon replanning utilities.

This module provides the core planning primitives for building multi-iteration schedules: slicing a
scenario into sub-horizons, tracking locked-in assignments, and constructing iteration plans that
advance the window by a configurable lock span. Solver integration (heuristics/MILP) will attach to
these primitives so both CLI and Python callers share the same orchestration layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

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
