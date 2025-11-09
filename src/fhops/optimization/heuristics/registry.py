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

    def register(self, operator: Operator) -> None:
        """Register or replace an operator."""
        self._operators[operator.name] = operator

    def get(self, name: str) -> Operator:
        """Return an operator by name."""
        try:
            return self._operators[name]
        except KeyError as exc:  # pragma: no cover - defensive; tests cover the positive path
            raise KeyError(f"Operator '{name}' is not registered") from exc

    def enabled(self) -> Iterable[Operator]:
        """Yield operators flagged with weight > 0."""
        return (op for op in self._operators.values() if op.weight > 0)

    def configure(self, weights: dict[str, float]) -> None:
        """Update weights (0 disables) for a subset of operators."""
        for name, weight in weights.items():
            op = self.get(name)
            op.weight = max(0.0, float(weight))

    @classmethod
    def from_defaults(cls, operators: Iterable[Operator]) -> OperatorRegistry:
        registry = cls()
        for op in operators:
            registry.register(op)
        return registry


__all__ = ["OperatorContext", "Sanitizer", "Operator", "OperatorRegistry"]
