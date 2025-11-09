"""Operator registry primitives for heuristic solvers."""

from __future__ import annotations

from collections.abc import Callable
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


__all__ = ["OperatorContext", "Sanitizer"]
