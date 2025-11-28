"""Operator registry primitives for heuristic solvers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations
from random import Random
from typing import TYPE_CHECKING, Any, Protocol

from fhops.scenario.contract import Problem

if TYPE_CHECKING:
    from fhops.optimization.heuristics.sa import Schedule
else:  # pragma: no cover - runtime placeholder to keep annotations happy

    class Schedule:  # type: ignore[too-many-ancestors]
        ...


Sanitizer = Callable[[Schedule], Schedule]


@dataclass(slots=True)
class OperatorContext:
    """Execution context passed to heuristic operators."""

    problem: Problem
    schedule: Schedule
    sanitizer: Sanitizer
    rng: Random
    distance_lookup: Mapping[tuple[str, str], float] | None = None
    block_windows: Mapping[str, tuple[int, int]] | None = None
    landing_capacity: Mapping[str, int] | None = None
    landing_of: Mapping[str, str] | None = None
    mobilisation_budget: Mapping[str, float] | None = None
    cooldown_tracker: Mapping[str, Any] | None = None


class Operator(Protocol):
    """Interface for heuristic operators."""

    name: str
    weight: float

    def apply(self, context: OperatorContext) -> Schedule | None:
        """Return a new schedule or None if the operator cannot generate a move."""


class OperatorRegistry:
    """Container for heuristic operators with enable/weight controls."""

    def __init__(self) -> None:
        self._operators: dict[str, Operator] = {}
        self._weights: dict[str, float] = {}

    def register(self, operator: Operator) -> None:
        """Register or replace an operator."""
        self._operators[operator.name] = operator
        self._weights.setdefault(operator.name, operator.weight)

    def get(self, name: str) -> Operator:
        """Return an operator by name."""
        try:
            return self._operators[name]
        except KeyError as exc:  # pragma: no cover - defensive; tests cover the positive path
            raise KeyError(f"Operator '{name}' is not registered") from exc

    def names(self) -> list[str]:
        """Return all registered operator names."""
        return list(self._operators.keys())

    def weights(self) -> dict[str, float]:
        """Return the current weight mapping."""
        return {name: self._weights.get(name, op.weight) for name, op in self._operators.items()}

    def enabled(self) -> Iterable[Operator]:
        """Yield operators flagged with weight > 0."""
        for name, operator in self._operators.items():
            weight = self._weights.get(name, operator.weight)
            if weight > 0:
                operator.weight = weight
                yield operator

    def configure(self, weights: dict[str, float]) -> None:
        """Update weights (0 disables) for a subset of operators."""
        for name, weight in weights.items():
            op = self.get(name)
            new_weight = max(0.0, float(weight))
            op.weight = new_weight
            self._weights[name] = new_weight

    @classmethod
    def from_defaults(cls, operators: Iterable[Operator] | None = None) -> OperatorRegistry:
        registry = cls()
        if operators is None:
            operators = (
                SwapOperator(),
                MoveOperator(),
                BlockInsertionOperator(weight=0.6),
                CrossExchangeOperator(weight=0.6),
                MobilisationShakeOperator(weight=0.2),
            )
        for op in operators:
            registry.register(op)
        return registry


def _clone_plan(schedule: Schedule) -> dict[str, dict[tuple[int, str], str | None]]:
    """Deep-copy the schedule plan so operators can mutate assignments safely."""
    return {machine: assignments.copy() for machine, assignments in schedule.plan.items()}


def _locked_assignments(problem: Problem) -> dict[tuple[str, int], str]:
    """Return a lookup of (machine, day) → block IDs that must remain fixed."""
    locks = getattr(problem.scenario, "locked_assignments", None)
    if not locks:
        return {}
    return {(lock.machine_id, lock.day): lock.block_id for lock in locks}


def _production_rates(problem: Problem) -> dict[tuple[str, str], float]:
    """Map (machine, block) pairs to their production rates."""
    return {
        (rate.machine_id, rate.block_id): rate.rate for rate in problem.scenario.production_rates
    }


def _block_window(block_id: str, context: OperatorContext) -> tuple[int, int] | None:
    """Return the allowable day window for a block, if block windows are configured."""
    if context.block_windows is None:
        return None
    return context.block_windows.get(block_id)


def _window_allows(day: int, block_id: str, context: OperatorContext) -> bool:
    """Check whether a block may be worked on the specified day."""
    window = _block_window(block_id, context)
    if window is None:
        return True
    start, end = window
    return start <= day <= end


def _plan_equals(
    plan_a: dict[str, dict[tuple[int, str], str | None]],
    plan_b: dict[str, dict[tuple[int, str], str | None]],
) -> bool:
    """Compare two machine→shift assignment maps for equality."""
    if plan_a.keys() != plan_b.keys():
        return False
    for machine in plan_a:
        if plan_a[machine] != plan_b[machine]:
            return False
    return True


class SwapOperator:
    """Swap the assignments of two machines on a random shift."""

    name: str = "swap"
    weight: float

    def __init__(self, weight: float = 1.0) -> None:
        self.weight = weight

    def apply(self, context: OperatorContext) -> Schedule | None:
        problem = context.problem
        machines = [machine.id for machine in problem.scenario.machines]
        if len(machines) < 2:
            return None
        shifts = [(s.day, s.shift_id) for s in problem.shifts]
        if not shifts:
            return None
        rng = context.rng
        shift_key = rng.choice(shifts)
        try:
            machine_pair = rng.sample(machines, k=2)
        except ValueError:
            return None
        new_plan = _clone_plan(context.schedule)
        m1, m2 = machine_pair
        new_plan[m1] = new_plan[m1].copy()
        new_plan[m2] = new_plan[m2].copy()
        new_plan[m1][shift_key], new_plan[m2][shift_key] = (
            new_plan[m2][shift_key],
            new_plan[m1][shift_key],
        )
        schedule_cls = context.schedule.__class__
        candidate = schedule_cls(plan=new_plan)
        return context.sanitizer(candidate)


class MoveOperator:
    """Move a machine assignment from one shift to another."""

    name: str = "move"
    weight: float

    def __init__(self, weight: float = 1.0) -> None:
        self.weight = weight

    def apply(self, context: OperatorContext) -> Schedule | None:
        schedule = context.schedule
        machines = list(schedule.plan.keys())
        if not machines:
            return None
        rng = context.rng
        machine = rng.choice(machines)
        shift_keys = list(schedule.plan[machine].keys())
        if not shift_keys:
            return None
        if len(shift_keys) >= 2:
            from_shift, to_shift = rng.sample(shift_keys, k=2)
        else:
            from_shift = to_shift = shift_keys[0]
        new_plan = _clone_plan(schedule)
        new_plan[machine] = new_plan[machine].copy()
        new_plan[machine][to_shift] = new_plan[machine][from_shift]
        new_plan[machine][from_shift] = None
        schedule_cls = schedule.__class__
        candidate = schedule_cls(plan=new_plan)
        return context.sanitizer(candidate)


class BlockInsertionOperator:
    """Relocate a block assignment to a different machine/shift within windows."""

    name: str = "block_insertion"
    weight: float

    def __init__(self, weight: float = 0.0) -> None:
        self.weight = weight

    def apply(self, context: OperatorContext) -> Schedule | None:
        schedule = context.schedule
        pb = context.problem
        rng = context.rng
        locks = _locked_assignments(pb)
        production = _production_rates(pb)
        machines = list(schedule.plan.keys())
        if not machines:
            return None
        assignments: list[tuple[str, tuple[int, str], str]] = [
            (machine, shift_key, block_id)
            for machine, machine_plan in schedule.plan.items()
            for shift_key, block_id in machine_plan.items()
            if block_id is not None and locks.get((machine, shift_key[0])) != block_id
        ]
        if not assignments:
            return None
        rng.shuffle(assignments)
        shifts = [(shift.day, shift.shift_id) for shift in pb.shifts]
        if not shifts:
            return None
        for machine_src, shift_src, block_id in assignments:
            candidate_targets: list[tuple[str, tuple[int, str]]] = []
            for machine_tgt in machines:
                for shift_day, shift_id in shifts:
                    if machine_tgt == machine_src and (shift_day, shift_id) == shift_src:
                        continue
                    if not _window_allows(shift_day, block_id, context):
                        continue
                    lock_key = (machine_tgt, shift_day)
                    locked_block = locks.get(lock_key)
                    if locked_block is not None and locked_block != block_id:
                        continue
                    if production.get((machine_tgt, block_id), 0.0) <= 0.0:
                        continue
                    candidate_targets.append((machine_tgt, (shift_day, shift_id)))
            rng.shuffle(candidate_targets)
            for machine_tgt, shift_tgt in candidate_targets:
                new_plan = _clone_plan(schedule)
                new_plan[machine_src] = new_plan[machine_src].copy()
                new_plan[machine_src][shift_src] = None
                new_plan[machine_tgt] = new_plan[machine_tgt].copy()
                new_plan[machine_tgt][shift_tgt] = block_id
                schedule_cls = schedule.__class__
                candidate = context.sanitizer(schedule_cls(plan=new_plan))
                if _plan_equals(candidate.plan, schedule.plan):
                    continue
                if candidate.plan.get(machine_tgt, {}).get(shift_tgt) != block_id:
                    continue
                return candidate
        return None


class CrossExchangeOperator:
    """Exchange two assignments across machines/shifts to rebalance workload."""

    name: str = "cross_exchange"
    weight: float

    def __init__(self, weight: float = 0.0) -> None:
        self.weight = weight

    def apply(self, context: OperatorContext) -> Schedule | None:
        schedule = context.schedule
        pb = context.problem
        rng = context.rng
        locks = _locked_assignments(pb)
        production = _production_rates(pb)
        assignments: list[tuple[str, tuple[int, str], str]] = [
            (machine, shift_key, block_id)
            for machine, machine_plan in schedule.plan.items()
            for shift_key, block_id in machine_plan.items()
            if block_id is not None
        ]
        if len(assignments) < 2:
            return None
        rng.shuffle(assignments)
        pairs = list(combinations(assignments, 2))
        rng.shuffle(pairs)
        for (machine_a, shift_a, block_a), (machine_b, shift_b, block_b) in pairs:
            if machine_a == machine_b:
                continue
            lock_a = locks.get((machine_a, shift_a[0]))
            lock_b = locks.get((machine_b, shift_b[0]))
            if lock_a == block_a or lock_b == block_b:
                continue
            if production.get((machine_a, block_b), 0.0) <= 0.0:
                continue
            if production.get((machine_b, block_a), 0.0) <= 0.0:
                continue
            if not _window_allows(shift_a[0], block_b, context):
                continue
            if not _window_allows(shift_b[0], block_a, context):
                continue
            new_plan = _clone_plan(schedule)
            new_plan[machine_a] = new_plan[machine_a].copy()
            new_plan[machine_b] = new_plan[machine_b].copy()
            new_plan[machine_a][shift_a] = block_b
            new_plan[machine_b][shift_b] = block_a
            schedule_cls = schedule.__class__
            candidate = context.sanitizer(schedule_cls(plan=new_plan))
            if _plan_equals(candidate.plan, schedule.plan):
                continue
            if candidate.plan.get(machine_a, {}).get(shift_a) != block_b:
                continue
            if candidate.plan.get(machine_b, {}).get(shift_b) != block_a:
                continue
            return candidate
        return None


class MobilisationShakeOperator:
    """Diversification move favouring high mobilisation distance shifts."""

    name: str = "mobilisation_shake"
    weight: float

    def __init__(self, weight: float = 0.0, min_day_delta: int = 1) -> None:
        self.weight = weight
        self.min_day_delta = min_day_delta

    def apply(self, context: OperatorContext) -> Schedule | None:
        schedule = context.schedule
        pb = context.problem
        rng = context.rng
        locks = _locked_assignments(pb)
        production = _production_rates(pb)
        distance_lookup = context.distance_lookup or {}
        machines = list(schedule.plan.keys())
        if not machines:
            return None
        assignments: list[tuple[str, tuple[int, str], str]] = [
            (machine, shift_key, block_id)
            for machine, machine_plan in schedule.plan.items()
            for shift_key, block_id in machine_plan.items()
            if block_id is not None and locks.get((machine, shift_key[0])) != block_id
        ]
        if not assignments:
            return None
        rng.shuffle(assignments)
        for machine_src, shift_src, block_id in assignments:
            day_src = shift_src[0]
            candidate_targets: list[tuple[float, int, str, tuple[int, str]]] = []
            for machine_tgt in machines:
                for shift_tgt, current_block in schedule.plan[machine_tgt].items():
                    if machine_tgt == machine_src and shift_tgt == shift_src:
                        continue
                    day_tgt = shift_tgt[0]
                    day_delta = abs(day_tgt - day_src)
                    if day_delta < self.min_day_delta:
                        continue
                    if not _window_allows(day_tgt, block_id, context):
                        continue
                    lock_key = (machine_tgt, day_tgt)
                    locked_block = locks.get(lock_key)
                    if locked_block is not None and locked_block != block_id:
                        continue
                    if production.get((machine_tgt, block_id), 0.0) <= 0.0:
                        continue
                    distance = 0.0
                    if current_block is not None and current_block != block_id:
                        distance = distance_lookup.get((block_id, current_block), 0.0)
                    candidate_targets.append((distance, day_delta, machine_tgt, shift_tgt))
            if not candidate_targets:
                continue
            rng.shuffle(candidate_targets)
            candidate_targets.sort(key=lambda item: (item[0], item[1]), reverse=True)
            for _, _, machine_tgt, shift_tgt in candidate_targets:
                new_plan = _clone_plan(schedule)
                new_plan[machine_src] = new_plan[machine_src].copy()
                new_plan[machine_src][shift_src] = None
                new_plan[machine_tgt] = new_plan[machine_tgt].copy()
                new_plan[machine_tgt][shift_tgt] = block_id
                schedule_cls = schedule.__class__
                candidate = context.sanitizer(schedule_cls(plan=new_plan))
                if _plan_equals(candidate.plan, schedule.plan):
                    continue
                if candidate.plan.get(machine_tgt, {}).get(shift_tgt) != block_id:
                    continue
                return candidate
        return None


__all__ = [
    "OperatorContext",
    "Sanitizer",
    "Operator",
    "OperatorRegistry",
    "SwapOperator",
    "MoveOperator",
    "BlockInsertionOperator",
    "CrossExchangeOperator",
    "MobilisationShakeOperator",
]
