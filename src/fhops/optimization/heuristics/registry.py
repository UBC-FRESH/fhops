"""Operator registry primitives for heuristic solvers."""

from __future__ import annotations

from bisect import insort
from collections import defaultdict
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
    shift_keys: tuple[tuple[int, str], ...]
    shift_index: Mapping[tuple[int, str], int]
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
                CoverageInjectionOperator(weight=0.5),
                CrossExchangeOperator(weight=0.6),
                MobilisationShakeOperator(weight=0.2),
            )
        for op in operators:
            registry.register(op)
        return registry


def _clone_schedule(
    context: OperatorContext,
    machines_to_copy: set[str] | None = None,
) -> Schedule:
    """Clone schedule plan/matrix, copying only the machines that will be mutated when provided."""

    schedule = context.schedule
    shift_keys = context.shift_keys
    if not machines_to_copy:
        plan = {machine: assignments.copy() for machine, assignments in schedule.plan.items()}
        matrix = {
            machine: row[:] if row is not None else [plan[machine].get(key) for key in shift_keys]
            for machine, row in schedule.matrix.items()
        }
        for machine in plan:
            matrix.setdefault(machine, [plan[machine].get(key) for key in shift_keys])
        clone = schedule.__class__(plan=plan, matrix=matrix)
        clone.mobilisation_cache = {}
        for machine, stats in schedule.mobilisation_cache.items():
            if stats is None:
                continue
            clone.mobilisation_cache[machine] = stats.__class__(stats.cost, stats.transitions)
        clone.dirty_machines = set(schedule.dirty_machines)
        clone.block_slots = {
            block: entries.copy() for block, entries in schedule.block_slots.items()
        }
        clone.dirty_slots = set(schedule.dirty_slots)
        if schedule.block_remaining_cache is not None:
            clone.block_remaining_cache = dict(schedule.block_remaining_cache)
        if schedule.role_remaining_cache is not None:
            clone.role_remaining_cache = dict(schedule.role_remaining_cache)
        if schedule.slot_production:
            clone.slot_production = {
                key: value.__class__(
                    block_id=value.block_id,
                    role=value.role,
                    block_volume=value.block_volume,
                    role_volume=value.role_volume,
                )
                for key, value in schedule.slot_production.items()
            }
        return clone

    plan = schedule.plan.copy()
    matrix = schedule.matrix.copy()
    for machine in machines_to_copy:
        assignments = schedule.plan.get(machine, {})
        plan[machine] = assignments.copy()
        row = schedule.matrix.get(machine)
        if row is None or len(row) != len(shift_keys):
            row = [assignments.get(key) for key in shift_keys]
        else:
            row = row[:]
        matrix[machine] = row
    clone = schedule.__class__(plan=plan, matrix=matrix)
    clone.mobilisation_cache = dict(schedule.mobilisation_cache)
    for machine in machines_to_copy:
        clone.mobilisation_cache.pop(machine, None)
    clone.dirty_machines = set(schedule.dirty_machines).union(machines_to_copy)
    clone.block_slots = {block: entries.copy() for block, entries in schedule.block_slots.items()}
    clone.dirty_slots = set(schedule.dirty_slots)
    if schedule.block_remaining_cache is not None:
        clone.block_remaining_cache = dict(schedule.block_remaining_cache)
    if schedule.role_remaining_cache is not None:
        clone.role_remaining_cache = dict(schedule.role_remaining_cache)
    if schedule.slot_production:
        clone.slot_production = {
            key: value.__class__(
                block_id=value.block_id,
                role=value.role,
                block_volume=value.block_volume,
                role_volume=value.role_volume,
            )
            for key, value in schedule.slot_production.items()
        }
    return clone


def _set_slot(
    context: OperatorContext,
    schedule: Schedule,
    machine_id: str,
    shift_key: tuple[int, str],
    block_id: str | None,
) -> None:
    """Set a single machine/shift assignment on the cloned schedule."""

    assignments = schedule.plan.setdefault(machine_id, {})
    old_block = assignments.get(shift_key)
    if old_block == block_id:
        return
    assignments[shift_key] = block_id
    row = schedule.matrix.setdefault(machine_id, [None] * len(context.shift_keys))
    shift_idx = context.shift_index[shift_key]
    row[shift_idx] = block_id
    slots = schedule.block_slots
    if slots:
        if old_block:
            entries = slots.get(old_block)
            if entries is not None:
                try:
                    entries.remove((shift_idx, machine_id))
                except ValueError:
                    pass
                if not entries:
                    slots.pop(old_block, None)
        if block_id:
            insort(slots.setdefault(block_id, []), (shift_idx, machine_id))
    if block_id and block_id != old_block:
        schedule.dirty_blocks.add(block_id)
    if old_block and old_block != block_id:
        schedule.dirty_blocks.add(old_block)
    schedule.dirty_slots.add((machine_id, shift_key[0], shift_key[1]))


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
        shifts = context.shift_keys
        if not shifts:
            return None
        rng = context.rng
        shift_key = rng.choice(shifts)
        try:
            machine_pair = rng.sample(machines, k=2)
        except ValueError:
            return None
        m1, m2 = machine_pair
        candidate = _clone_schedule(context, {m1, m2})
        val1 = candidate.plan[m1].get(shift_key)
        val2 = candidate.plan[m2].get(shift_key)
        _set_slot(context, candidate, m1, shift_key, val2)
        _set_slot(context, candidate, m2, shift_key, val1)
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
        candidate = _clone_schedule(context, {machine})
        value = candidate.plan[machine].get(from_shift)
        _set_slot(context, candidate, machine, to_shift, value)
        _set_slot(context, candidate, machine, from_shift, None)
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
        shifts = context.shift_keys
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
                candidate = _clone_schedule(context, {machine_src, machine_tgt})
                _set_slot(context, candidate, machine_src, shift_src, None)
                _set_slot(context, candidate, machine_tgt, shift_tgt, block_id)
                candidate = context.sanitizer(candidate)
                if _plan_equals(candidate.plan, schedule.plan):
                    continue
                if candidate.plan.get(machine_tgt, {}).get(shift_tgt) != block_id:
                    continue
                return candidate
        return None


class CoverageInjectionOperator:
    """Inject high-deficit blocks into candidate shifts to boost coverage."""

    name: str = "coverage_injection"
    weight: float

    def __init__(self, weight: float = 0.0) -> None:
        self.weight = weight

    def apply(self, context: OperatorContext) -> Schedule | None:
        schedule = context.schedule
        pb = context.problem
        production = _production_rates(pb)
        work_required = {block.id: block.work_required for block in pb.scenario.blocks}
        locks = _locked_assignments(pb)
        capacities: defaultdict[str, float] = defaultdict(float)
        assignments: defaultdict[str, list[tuple[str, tuple[int, str]]]] = defaultdict(list)
        idle_slots: list[tuple[str, tuple[int, str]]] = []

        for machine_id, machine_plan in schedule.plan.items():
            for shift_key, block_id in machine_plan.items():
                if block_id is None:
                    idle_slots.append((machine_id, shift_key))
                    continue
                rate_value = production.get((machine_id, block_id), 0.0)
                if rate_value <= 0.0:
                    idle_slots.append((machine_id, shift_key))
                    continue
                capacities[block_id] += rate_value
                assignments[block_id].append((machine_id, shift_key))

        deficits = {
            block_id: required - capacities.get(block_id, 0.0)
            for block_id, required in work_required.items()
            if required - capacities.get(block_id, 0.0) > CAPACITY_EPS
        }
        if not deficits:
            return None
        target_block = max(deficits.items(), key=lambda item: item[1])[0]

        candidate_slots: list[tuple[float, str, tuple[int, str]]] = []
        rng = context.rng

        def _maybe_add_slot(machine_id: str, shift_key: tuple[int, str]) -> None:
            locked_block = locks.get((machine_id, shift_key[0]))
            if locked_block is not None and locked_block != target_block:
                return
            if not _window_allows(shift_key[0], target_block, context):
                return
            rate_value = production.get((machine_id, target_block), 0.0)
            if rate_value <= 0.0:
                return
            candidate_slots.append((rate_value, machine_id, shift_key))

        for machine_id, shift_key in idle_slots:
            _maybe_add_slot(machine_id, shift_key)
        for block_id, entries in assignments.items():
            surplus = capacities.get(block_id, 0.0) - work_required.get(block_id, 0.0)
            if surplus <= CAPACITY_EPS:
                continue
            for machine_id, shift_key in entries:
                _maybe_add_slot(machine_id, shift_key)

        if not candidate_slots:
            return None
        rng.shuffle(candidate_slots)
        candidate_slots.sort(key=lambda item: item[0], reverse=True)
        _, machine_id, shift_key = candidate_slots[0]
        candidate = _clone_schedule(context, {machine_id})
        _set_slot(context, candidate, machine_id, shift_key, target_block)
        candidate = context.sanitizer(candidate)
        if _plan_equals(candidate.plan, schedule.plan):
            return None
        if candidate.plan.get(machine_id, {}).get(shift_key) != target_block:
            return None
        return candidate


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
            candidate = _clone_schedule(context, {machine_a, machine_b})
            _set_slot(context, candidate, machine_a, shift_a, block_b)
            _set_slot(context, candidate, machine_b, shift_b, block_a)
            candidate = context.sanitizer(candidate)
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
                candidate = _clone_schedule(context, {machine_src, machine_tgt})
                _set_slot(context, candidate, machine_src, shift_src, None)
                _set_slot(context, candidate, machine_tgt, shift_tgt, block_id)
                candidate = context.sanitizer(candidate)
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
    "CoverageInjectionOperator",
    "CrossExchangeOperator",
    "MobilisationShakeOperator",
]
CAPACITY_EPS = 1e-6
