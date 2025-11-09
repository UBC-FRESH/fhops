"""Operator registry primitives for heuristic solvers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING

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


__all__ = ["OperatorContext", "Sanitizer"]
