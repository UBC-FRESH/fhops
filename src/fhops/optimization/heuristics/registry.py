"""Operator registry primitives for heuristic solvers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING, Protocol

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
            operators = (SwapOperator(), MoveOperator())
        for op in operators:
            registry.register(op)
        return registry


def _clone_plan(schedule: Schedule) -> dict[str, dict[tuple[int, str], str | None]]:
    return {machine: assignments.copy() for machine, assignments in schedule.plan.items()}


class SwapOperator:
    """Swap the assignments of two machines on a random shift."""

    name = "swap"

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

    name = "move"

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


__all__ = [
    "OperatorContext",
    "Sanitizer",
    "Operator",
    "OperatorRegistry",
    "SwapOperator",
    "MoveOperator",
]
