"""The FHOPS adapter for the shared metaheuristic kernel.

FHOPS keeps its machine-by-slot schedule, repair/sanitizer, operational problem, and
objective. This module supplies the kernel boundary: an adapter-owned state, a move
context, kernel operators that wrap the existing FHOPS operators, and exact replayable
results.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from fresh_solutions.kernel import Operator, OperatorRegistry, Problem

from fhops.optimization.heuristics.common import (
    Schedule,
    evaluate_schedule,
    init_greedy_schedule,
    resolve_objective_weight_overrides,
)
from fhops.optimization.heuristics.registry import OperatorContext
from fhops.optimization.heuristics.registry import OperatorRegistry as FhopsRegistry
from fhops.optimization.operational_problem import (
    OperationalProblem,
    build_operational_problem,
    override_objective_weights,
)
from fhops.scenario.contract import Problem as ScenarioProblem

Slot = tuple[str, int, str]


@dataclass(frozen=True)
class FhopsContext:
    """The adapter-owned move context: the scenario and its operational lookups.

    Attributes
    ----------
    pb : ScenarioProblem
        The parsed scenario.
    operational : OperationalProblem
        The shared operational context (shift keys, windows, landings, sanitizer).
    """

    pb: ScenarioProblem
    operational: OperationalProblem


class FhopsOperatorProtocol(Protocol):
    """The part of a FHOPS operator the adapter uses."""

    name: str
    weight: float

    def apply(self, context: OperatorContext) -> Schedule | None:
        """Return a candidate schedule, or ``None``."""
        ...


class FhopsOperator:
    """A FHOPS neighbourhood operator exposed through the kernel protocol.

    Parameters
    ----------
    operator : FhopsOperatorProtocol
        A FHOPS operator with ``name``, ``weight``, and ``apply(context)``.
    operational : OperationalProblem
        The operational context used to build each call's ``OperatorContext``.
    """

    def __init__(self, operator: FhopsOperatorProtocol, operational: OperationalProblem) -> None:
        self._operator = operator
        self._operational = operational
        self.name = str(operator.name)
        self.weight = float(operator.weight)

    def _context(self, schedule: Schedule, rng: random.Random) -> OperatorContext:
        """Build the FHOPS operator context for one proposal."""
        ctx = self._operational
        return OperatorContext(
            problem=ctx.problem,
            schedule=schedule,
            sanitizer=ctx.build_sanitizer(schedule.__class__),
            rng=rng,
            shift_keys=ctx.shift_keys,
            shift_index=ctx.shift_index,
            distance_lookup=ctx.distance_lookup,
            block_windows=ctx.bundle.windows,
            landing_capacity=ctx.bundle.landing_capacity,
            landing_of=ctx.bundle.landing_for_block,
            sanitizer_preview=ctx.build_sanitizer_preview(schedule.plan),
        )

    def apply(self, state: Schedule, rng: random.Random, context: FhopsContext) -> Schedule | None:
        """Return the candidate schedule the wrapped FHOPS operator proposes.

        Parameters
        ----------
        state : Schedule
            The current schedule.
        rng : random.Random
            The random source.
        context : FhopsContext
            The adapter context.

        Returns
        -------
        Schedule or None
            The proposed schedule, or ``None`` when the operator cannot move.
        """
        return self._operator.apply(self._context(state, rng))

    def propose_inplace(
        self, state: Schedule, rng: random.Random, context: FhopsContext
    ) -> Mapping[int, object] | None:
        """Reject the in-place path; FHOPS operators return copied schedules.

        Raises
        ------
        NotImplementedError
            Always. The kernel's whole-schedule solvers use :meth:`apply`.
        """
        raise NotImplementedError("FHOPS operators use the copying apply path")


def slot_diff(before: Schedule, after: Schedule) -> frozenset[Slot]:
    """Return the machine/day/shift slots whose block assignment changed.

    Parameters
    ----------
    before : Schedule
        The schedule before the move.
    after : Schedule
        The schedule after the move.

    Returns
    -------
    frozenset of (str, int, str)
        The changed slots.
    """
    changed: set[Slot] = set()
    machines = set(before.plan) | set(after.plan)
    for machine_id in machines:
        old = before.plan.get(machine_id, {})
        new = after.plan.get(machine_id, {})
        for day, shift_id in set(old) | set(new):
            if old.get((day, shift_id)) != new.get((day, shift_id)):
                changed.add((machine_id, day, shift_id))
    return frozenset(changed)


class FhopsProblem(Problem[Schedule, FhopsContext]):
    """The FHOPS problem passed to the shared kernel.

    Parameters
    ----------
    pb : ScenarioProblem
        The parsed scenario.
    operators : sequence of str or None, optional
        Operator names to enable. ``None`` enables the FHOPS defaults.
    operator_weights : mapping of str to float or None, optional
        Weight overrides. Values at or below zero disable an operator.
    objective_weight_overrides : mapping of str to float or None, optional
        Objective weights to override. ``None`` applies the FHOPS automatic overrides for
        Tiny7/Small21, matching the existing solvers.
    """

    def __init__(
        self,
        pb: ScenarioProblem,
        operators: list[str] | None = None,
        operator_weights: dict[str, float] | None = None,
        objective_weight_overrides: dict[str, float] | None = None,
    ) -> None:
        operational = build_operational_problem(pb)
        resolved_overrides = resolve_objective_weight_overrides(pb, objective_weight_overrides)
        if resolved_overrides:
            operational = override_objective_weights(operational, resolved_overrides)
        self.objective_weight_overrides = resolved_overrides
        self.requested_objective_weight_overrides = objective_weight_overrides
        fhops_registry = FhopsRegistry.from_defaults()
        available = {name.lower(): name for name in fhops_registry.names()}
        if operators:
            requested = {name.lower() for name in operators}
            unknown = requested - set(available)
            if unknown:
                raise ValueError(f"unknown operators: {', '.join(sorted(unknown))}")
            for lower, name in available.items():
                if lower not in requested:
                    operator_weights = dict(operator_weights or {})
                    operator_weights[name] = 0.0
        if operator_weights:
            fhops_registry.configure(operator_weights)
        kernel_operators: list[Operator[Schedule, FhopsContext]] = [
            FhopsOperator(fhops_registry.get(name), operational)
            for name in fhops_registry.names()
            if fhops_registry.weights()[name] > 0.0
        ]
        registry: OperatorRegistry[Schedule, FhopsContext] = OperatorRegistry(kernel_operators)
        self.pb = pb
        self.operational = operational
        self.fhops_registry = fhops_registry
        context = FhopsContext(pb=pb, operational=operational)
        super().__init__(
            evaluate=self._evaluate,
            candidates=context,
            registry=registry,
            empty=self.greedy_schedule,
            clone=copy.deepcopy,
            signature=slot_diff,
        )

    def _evaluate(self, schedule: Schedule) -> float:
        """Return the negated FHOPS objective, because the kernel minimizes.

        Parameters
        ----------
        schedule : Schedule
            The schedule to score. FHOPS repairs it in place before scoring.

        Returns
        -------
        float
            The negated FHOPS objective.
        """
        return -evaluate_schedule(self.pb, schedule, self.operational)

    def greedy_schedule(self) -> Schedule:
        """Return the FHOPS greedy starting schedule.

        Returns
        -------
        Schedule
            The greedy schedule.
        """
        return init_greedy_schedule(self.pb, self.operational)
