"""Kernel-backed solvers for FHOPS.

The first integration exposes simulated annealing through the shared kernel. FHOPS keeps
its existing solvers until each kernel-backed path clears the parity and performance gates;
this module is the adapter proof, not a replacement yet.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Any

import pandas as pd
from fresh_solutions.kernel import (
    TemperatureSchedule,
    patience_reached,
    reversion_due,
    solve_ils,
    solve_sa,
    solve_tabu,
)

from fhops.optimization.heuristics.common import (
    Schedule,
    _repair_schedule_cover_blocks,
    evaluate_schedule,
)
from fhops.optimization.heuristics.incremental import SeparableEvaluator, slot_diff
from fhops.scenario.contract import Problem

from .adapter import FhopsProblem

ASSIGNMENT_COLUMNS = ["machine_id", "block_id", "day", "shift_id", "assigned"]


def _result(
    pb: Problem,
    problem: FhopsProblem,
    schedule: Schedule,
    greedy_score: float,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Rescore a kernel result exactly and return the FHOPS result payload."""
    objective = evaluate_schedule(pb, schedule, problem.operational)
    solver = str(meta.pop("solver"))
    payload: dict[str, Any] = {
        "solver": solver,
        "operators": problem.registry.weights(),
        "greedy_objective": float(greedy_score),
        "objective_delta_vs_greedy": float(objective - greedy_score),
    }
    payload.update(meta)
    return {
        "objective": float(objective),
        "assignments": schedule_assignments(schedule),
        "meta": payload,
        "schedule": schedule,
    }


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
    return _result(
        pb,
        problem,
        best,
        greedy_score,
        {
            "solver": "kernel-sa",
            "iterations": iters,
            "seed": seed,
            "temperature": start_temperature,
            "cooling": cooling,
        },
    )


def solve_kernel_tabu(
    pb: Problem,
    *,
    iters: int = 2000,
    seed: int = 42,
    tenure: int | None = None,
    samples: int = 8,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run the shared kernel's tabu search over a FHOPS scenario.

    Parameters
    ----------
    pb : Problem
        The parsed FHOPS scenario.
    iters : int, optional
        The iteration budget. Defaults to 2000.
    seed : int, optional
        The random seed. Defaults to 42.
    tenure : int or None, optional
        The tabu tenure. ``None`` uses twice the machine count, at least five.
    samples : int, optional
        The candidate moves sampled per iteration. Defaults to 8.
    operators : list of str or None, optional
        Operator names to enable. ``None`` enables the FHOPS defaults.
    operator_weights : mapping of str to float or None, optional
        Weight overrides. Values at or below zero disable an operator.

    Returns
    -------
    dict of str to Any
        The same payload as :func:`solve_kernel_sa`.
    """
    problem = FhopsProblem(pb, operators=operators, operator_weights=operator_weights)
    initial = problem.greedy_schedule()
    greedy_score = evaluate_schedule(pb, initial, problem.operational)
    resolved_tenure = max(5, 2 * len(pb.scenario.machines)) if tenure is None else tenure
    best, _negated = solve_tabu(
        problem,
        random.Random(seed),
        iterations=iters,
        tenure=resolved_tenure,
        samples=samples,
        initial=initial,
    )
    return _result(
        pb,
        problem,
        best,
        greedy_score,
        {
            "solver": "kernel-tabu",
            "iterations": iters,
            "seed": seed,
            "tenure": resolved_tenure,
            "samples": samples,
        },
    )


def solve_kernel_ils(
    pb: Problem,
    *,
    iters: int = 50,
    seed: int = 42,
    perturbation: int = 3,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run the shared kernel's iterated local search over a FHOPS scenario.

    Parameters
    ----------
    pb : Problem
        The parsed FHOPS scenario.
    iters : int, optional
        The outer iteration budget. Defaults to 50.
    seed : int, optional
        The random seed. Defaults to 42.
    perturbation : int, optional
        The moves per perturbation. Defaults to 3.
    operators : list of str or None, optional
        Operator names to enable. ``None`` enables the FHOPS defaults.
    operator_weights : mapping of str to float or None, optional
        Weight overrides. Values at or below zero disable an operator.

    Returns
    -------
    dict of str to Any
        The same payload as :func:`solve_kernel_sa`.
    """
    problem = FhopsProblem(pb, operators=operators, operator_weights=operator_weights)
    initial = problem.greedy_schedule()
    greedy_score = evaluate_schedule(pb, initial, problem.operational)
    best, _negated = solve_ils(
        problem,
        random.Random(seed),
        iterations=iters,
        perturbation=perturbation,
        initial=initial,
    )
    return _result(
        pb,
        problem,
        best,
        greedy_score,
        {
            "solver": "kernel-ils",
            "iterations": iters,
            "seed": seed,
            "perturbation": perturbation,
        },
    )


def solve_kernel_sa_fast(
    pb: Problem,
    *,
    iters: int = 2000,
    seed: int = 42,
    temperature: float | None = None,
    cooling: float = 0.995,
    patience: int = 0,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run kernel annealing with FHOPS's dirty-slot repair path.

    This is the performance path. Candidate scoring repairs only the slots the operator
    touched (``limit_repairs_to_dirty``), while the returned schedule is always rescored with
    a full repair. That makes the search score approximate, exactly like the existing FHOPS
    ``use_local_repairs`` mode, and the reported objective exact.

    Parameters
    ----------
    pb : Problem
        The parsed FHOPS scenario.
    iters : int, optional
        The iteration budget. Defaults to 2000.
    seed : int, optional
        The random seed. Defaults to 42.
    temperature : float or None, optional
        The initial temperature. ``None`` uses ``max(1, greedy_score / 10)``.
    cooling : float, optional
        The geometric cooling factor. Defaults to 0.995.
    patience : int, optional
        Stop after this many iterations without improvement; ``0`` disables it.
    operators : list of str or None, optional
        Operator names to enable. ``None`` enables the FHOPS defaults.
    operator_weights : mapping of str to float or None, optional
        Weight overrides. Values at or below zero disable an operator.

    Returns
    -------
    dict of str to Any
        The same payload as :func:`solve_kernel_sa`, with ``meta["approximate_search"]`` set.
    """
    problem = FhopsProblem(pb, operators=operators, operator_weights=operator_weights)
    current = problem.greedy_schedule()
    greedy_score = evaluate_schedule(pb, current, problem.operational)
    current_obj = -evaluate_schedule(pb, current, problem.operational, limit_repairs_to_dirty=True)
    best = current
    best_obj = current_obj
    start_temperature = max(1.0, greedy_score / 10.0) if temperature is None else float(temperature)
    schedule = TemperatureSchedule(
        initial=start_temperature,
        cooling=cooling,
        adaptive=False,
        window=64,
    )
    rng = random.Random(seed)
    last_improvement = 0
    for iteration in range(iters):
        if patience_reached(iteration, last_improvement, patience):
            break
        move = problem.registry.pick(rng).apply(current, rng, problem.candidates)
        if move is None:
            schedule.observe(0.0, current_obj)
            continue
        move_obj = -evaluate_schedule(pb, move, problem.operational, limit_repairs_to_dirty=True)
        increase = move_obj - current_obj
        if move_obj <= current_obj or rng.random() < math.exp(
            (current_obj - move_obj) / max(schedule.temperature, 1e-9)
        ):
            current, current_obj = move, move_obj
            if move_obj < best_obj:
                best, best_obj = move, move_obj
                last_improvement = iteration
        schedule.observe(increase, current_obj)
    return _result(
        pb,
        problem,
        best,
        greedy_score,
        {
            "solver": "kernel-sa-fast",
            "iterations": iters,
            "seed": seed,
            "temperature": start_temperature,
            "cooling": cooling,
            "approximate_search": True,
        },
    )


def solve_kernel_sa_incremental(
    pb: Problem,
    *,
    iters: int = 2000,
    seed: int = 42,
    temperature: float | None = None,
    cooling: float = 0.995,
    patience: int = 0,
    reversion: int = 0,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run kernel annealing with exact block-separable incremental scoring.

    Each candidate is repaired fully, then only the blocks touched by the move are recomputed
    through :class:`~fhops.optimization.heuristics.incremental.SeparableEvaluator`. A rejected
    move rolls the evaluator cache back, so no full rescore is needed inside the loop. The returned
    schedule is always rescored with :func:`evaluate_schedule`.

    Parameters
    ----------
    pb : Problem
        The parsed FHOPS scenario.
    iters : int, optional
        The iteration budget. Defaults to 2000.
    seed : int, optional
        The random seed. Defaults to 42.
    temperature : float or None, optional
        The initial temperature. ``None`` uses ``max(1, greedy_score / 10)``.
    cooling : float, optional
        The geometric cooling factor. Defaults to 0.995.
    patience : int, optional
        Stop after this many iterations without improvement; ``0`` disables it.
    reversion : int, optional
        Reset to the incumbent every this many accepted moves; ``0`` disables it.
    operators : list of str or None, optional
        Operator names to enable. ``None`` enables the FHOPS defaults.
    operator_weights : mapping of str to float or None, optional
        Weight overrides. Values at or below zero disable an operator.

    Returns
    -------
    dict of str to Any
        The same payload as :func:`solve_kernel_sa`, with incremental-search metadata.
    """
    problem = FhopsProblem(pb, operators=operators, operator_weights=operator_weights)
    current = problem.greedy_schedule()
    _repair_schedule_cover_blocks(pb, current, problem.operational, fill_voids=True)
    evaluator = SeparableEvaluator(pb, problem.operational)
    current_score = evaluator.build(current)
    greedy_score = current_score
    best = current
    best_score = current_score
    start_temperature = max(1.0, greedy_score / 10.0) if temperature is None else float(temperature)
    schedule = TemperatureSchedule(
        initial=start_temperature,
        cooling=cooling,
        adaptive=False,
        window=64,
    )
    rng = random.Random(seed)
    last_improvement = 0
    accepted = 0
    for iteration in range(iters):
        if patience_reached(iteration, last_improvement, patience):
            break
        move = problem.registry.pick(rng).apply(current, rng, problem.candidates)
        if move is None:
            schedule.observe(0.0, -current_score)
            continue
        _repair_schedule_cover_blocks(pb, move, problem.operational, fill_voids=True)
        changed: Sequence[tuple[str, int, str]] = slot_diff(current, move)
        move_score = evaluator.score_after_move(move, list(changed))
        increase = current_score - move_score
        if move_score >= current_score or rng.random() < math.exp(
            (move_score - current_score) / max(schedule.temperature, 1e-9)
        ):
            current, current_score = move, move_score
            accepted += 1
            if move_score > best_score:
                best, best_score = move, move_score
                last_improvement = iteration
            if reversion_due(accepted, reversion):
                current, current_score = best, best_score
                evaluator.build(current)
                accepted = 0
        else:
            evaluator.undo_last_move(current)
        schedule.observe(increase, -current_score)
    return _result(
        pb,
        problem,
        best,
        greedy_score,
        {
            "solver": "kernel-sa-incremental",
            "iterations": iters,
            "seed": seed,
            "temperature": start_temperature,
            "cooling": cooling,
            "incremental_search": True,
        },
    )
