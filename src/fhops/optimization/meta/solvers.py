"""Kernel-backed solvers for FHOPS.

The first integration exposes simulated annealing through the shared kernel. FHOPS keeps
its existing solvers until each kernel-backed path clears the parity and performance gates;
this module is the adapter proof, not a replacement yet.
"""

from __future__ import annotations

import random
from typing import Any

import pandas as pd
from fresh_solutions.kernel import solve_sa

from fhops.optimization.heuristics.common import Schedule, evaluate_schedule
from fhops.scenario.contract import Problem

from .adapter import FhopsProblem

ASSIGNMENT_COLUMNS = ["machine_id", "block_id", "day", "shift_id", "assigned"]


def schedule_assignments(schedule: Schedule) -> pd.DataFrame:
    """Render a schedule as the FHOPS assignment table.

    Parameters
    ----------
    schedule : Schedule
        The schedule to export.

    Returns
    -------
    pandas.DataFrame
        Columns ``machine_id``, ``block_id``, ``day``, ``shift_id``, ``assigned``.
    """
    rows: list[dict[str, str | int]] = []
    for machine_id, plan in schedule.plan.items():
        for (day, shift_id), block_id in plan.items():
            if block_id is not None:
                rows.append(
                    {
                        "machine_id": machine_id,
                        "block_id": block_id,
                        "day": int(day),
                        "shift_id": shift_id,
                        "assigned": 1,
                    }
                )
    frame = pd.DataFrame(rows, columns=ASSIGNMENT_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["day", "shift_id", "machine_id", "block_id"])
    return frame


def solve_kernel_sa(
    pb: Problem,
    *,
    iters: int = 2000,
    seed: int = 42,
    temperature: float | None = None,
    cooling: float = 0.995,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run the shared kernel's simulated annealing over a FHOPS scenario.

    Parameters
    ----------
    pb : Problem
        The parsed FHOPS scenario.
    iters : int, optional
        The kernel iteration budget. Defaults to 2000.
    seed : int, optional
        The random seed. Defaults to 42.
    temperature : float or None, optional
        The initial temperature. ``None`` uses ``max(1, greedy_score / 10)``, as the
        FHOPS solver does.
    cooling : float, optional
        The geometric cooling factor. Defaults to 0.995.
    operators : list of str or None, optional
        Operator names to enable. ``None`` enables the FHOPS defaults.
    operator_weights : mapping of str to float or None, optional
        Weight overrides. Values at or below zero disable an operator.

    Returns
    -------
    dict of str to Any
        ``objective`` (the fresh FHOPS score), ``assignments`` (the assignment table),
        ``meta`` (configuration and counters), and ``schedule`` (the schedule object).
    """
    problem = FhopsProblem(pb, operators=operators, operator_weights=operator_weights)
    initial = problem.greedy_schedule()
    greedy_score = evaluate_schedule(pb, initial, problem.operational)
    start_temperature = max(1.0, greedy_score / 10.0) if temperature is None else float(temperature)
    best, _negated = solve_sa(
        problem,
        random.Random(seed),
        iterations=iters,
        temperature=start_temperature,
        cooling=cooling,
        initial=initial,
    )
    objective = evaluate_schedule(pb, best, problem.operational)
    return {
        "objective": float(objective),
        "assignments": schedule_assignments(best),
        "meta": {
            "solver": "kernel-sa",
            "iterations": iters,
            "seed": seed,
            "temperature": start_temperature,
            "cooling": cooling,
            "operators": problem.registry.weights(),
            "greedy_objective": float(greedy_score),
            "objective_delta_vs_greedy": float(objective - greedy_score),
        },
        "schedule": best,
    }
