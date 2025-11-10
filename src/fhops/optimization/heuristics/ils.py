"""Iterated Local Search / hybrid heuristic leveraging the operator registry."""

from __future__ import annotations

import random as _random
from typing import Any, cast

import pandas as pd

from fhops.optimization.heuristics.registry import OperatorRegistry
from fhops.optimization.heuristics.sa import (
    Schedule,
    _evaluate,
    _evaluate_candidates,
    _init_greedy,
    _neighbors,
)
from fhops.optimization.mip import solve_mip
from fhops.scenario.contract import Problem


def _assignments_to_schedule(pb: Problem, assignments: pd.DataFrame) -> Schedule:
    shifts = [(shift.day, shift.shift_id) for shift in pb.shifts]
    plan: dict[str, dict[tuple[int, str], str | None]] = {
        machine.id: {(day, shift_id): None for (day, shift_id) in shifts}
        for machine in pb.scenario.machines
    }
    for record in assignments.to_dict(orient="records"):
        machine_raw = record.get("machine_id")
        day_raw = record.get("day")
        shift_raw = record.get("shift_id")
        block_raw = record.get("block_id")
        if machine_raw is None or day_raw is None or shift_raw is None:
            continue
        machine_id = str(machine_raw)
        day_value: int
        if isinstance(day_raw, int | float):
            day_value = int(day_raw)
        elif isinstance(day_raw, str):
            try:
                day_value = int(day_raw)
            except ValueError:
                continue
        else:
            continue
        shift_id = str(shift_raw)
        block_id = cast(str | None, block_raw if block_raw is not None else None)
        if machine_id in plan:
            plan[machine_id][(day_value, shift_id)] = block_id
    return Schedule(plan=plan)


def _perturb_schedule(
    pb: Problem,
    schedule: Schedule,
    registry: OperatorRegistry,
    rng: _random.Random,
    strength: int,
    operator_stats: dict[str, dict[str, float]],
) -> Schedule:
    current = schedule
    for _ in range(max(1, strength)):
        neighbours = _neighbors(
            pb,
            current,
            registry,
            rng,
            operator_stats,
            batch_size=1,
        )
        if not neighbours:
            break
        current = rng.choice(neighbours)
    return current


def _local_search(
    pb: Problem,
    schedule: Schedule,
    registry: OperatorRegistry,
    rng: _random.Random,
    batch_size: int | None,
    max_workers: int | None,
    operator_stats: dict[str, dict[str, float]],
) -> tuple[Schedule, float, bool, int]:
    current = schedule
    current_score = _evaluate(pb, current)
    improved = False
    local_steps = 0
    while True:
        candidates = _neighbors(
            pb,
            current,
            registry,
            rng,
            operator_stats,
            batch_size=batch_size,
        )
        evaluations = _evaluate_candidates(pb, candidates, max_workers)
        if not evaluations:
            break

        best_candidate, best_score = max(evaluations, key=lambda x: x[1])
        if best_score > current_score:
            current = best_candidate
            current_score = best_score
            improved = True
            local_steps += 1
        else:
            break
    return current, current_score, improved, local_steps


def solve_ils(
    pb: Problem,
    *,
    iters: int = 50,
    seed: int = 42,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
    batch_size: int | None = None,
    max_workers: int | None = None,
    perturbation_strength: int = 3,
    stall_limit: int = 10,
    hybrid_use_mip: bool = False,
    hybrid_mip_time_limit: int = 60,
) -> dict[str, Any]:
    """Run Iterated Local Search (optionally with MIP warm starts).

    Parameters
    ----------
    pb:
        Parsed problem definition containing the schedule context.
    iters:
        Number of ILS outer iterations (local search + perturbation cycles).
    seed:
        Seed used for deterministic RNG behaviour.
    operators:
        Optional list of operator names to enable. Defaults to the registry defaults.
    operator_weights:
        Optional weight overrides for registered operators.
    batch_size:
        Number of neighbours sampled per local search step (``None`` keeps sequential sampling).
    max_workers:
        Worker pool size for evaluating batched neighbours (``None`` keeps sequential evaluation).
    perturbation_strength:
        Count of perturbation steps applied when diversification is required.
    stall_limit:
        Non-improving iterations before triggering perturbation or hybrid restart.
    hybrid_use_mip:
        When ``True`` attempt a time-boxed MIP warm start once stalls exceed the limit.
    hybrid_mip_time_limit:
        Time limit (seconds) forwarded to the hybrid MIP warm start.

    Returns
    -------
    dict
        Dictionary containing objective value, assignment DataFrame, and telemetry metadata.
    """

    rng = _random.Random(seed)
    registry = OperatorRegistry.from_defaults()
    available = {name.lower(): name for name in registry.names()}
    if operators:
        requested = {name.lower() for name in operators}
        unknown = requested - set(available)
        if unknown:
            raise ValueError(f"Unknown operators requested: {', '.join(sorted(unknown))}")
        disable = {available[name]: 0.0 for name in available if name not in requested}
        if disable:
            registry.configure(disable)
    if operator_weights:
        normalized: dict[str, float] = {}
        for name, weight in operator_weights.items():
            key = name.lower()
            if key not in available:
                raise ValueError(f"Unknown operator '{name}' in weights configuration")
            normalized[available[key]] = weight
        registry.configure(normalized)

    batch_arg = batch_size if batch_size and batch_size > 1 else None
    worker_arg = max_workers if max_workers and max_workers > 1 else None

    current = _init_greedy(pb)
    current_score = _evaluate(pb, current)
    best = current
    best_score = current_score
    initial_score = current_score

    stalls = 0
    perturbations = 0
    restarts = 0
    improvement_steps = 0
    operator_stats: dict[str, dict[str, float]] = {}

    for _ in range(max(1, iters)):
        current, current_score, improved, steps = _local_search(
            pb, current, registry, rng, batch_arg, worker_arg, operator_stats
        )
        improvement_steps += steps
        if current_score > best_score:
            best, best_score = current, current_score
            stalls = 0
        else:
            stalls += 1

        if stalls >= stall_limit:
            if hybrid_use_mip:
                try:
                    mip_res = solve_mip(
                        pb, time_limit=hybrid_mip_time_limit, driver="auto", debug=False
                    )
                    assignments = cast(pd.DataFrame, mip_res["assignments"]).copy()
                    hybrid_schedule = _assignments_to_schedule(pb, assignments)
                    hybrid_score = _evaluate(pb, hybrid_schedule)
                    if hybrid_score > best_score:
                        best, best_score = hybrid_schedule, hybrid_score
                        current = best
                        current_score = best_score
                        stalls = 0
                        restarts += 1
                        continue
                except Exception:  # pragma: no cover - defensive path
                    pass
            current = best
            current = _perturb_schedule(
                pb, current, registry, rng, perturbation_strength, operator_stats
            )
            current_score = _evaluate(pb, current)
            stall_limit = max(1, stall_limit)
            stalls = 0
            perturbations += 1
        else:
            current = _perturb_schedule(
                pb, current, registry, rng, perturbation_strength, operator_stats
            )
            current_score = _evaluate(pb, current)
            perturbations += 1

    rows = []
    for machine_id, plan in best.plan.items():
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
    assignments = pd.DataFrame(rows).sort_values(["day", "shift_id", "machine_id", "block_id"])
    meta = {
        "initial_score": float(initial_score),
        "best_score": float(best_score),
        "iterations": iters,
        "perturbations": perturbations,
        "restarts": restarts,
        "stall_limit": stall_limit,
        "perturbation_strength": perturbation_strength,
        "hybrid_used": hybrid_use_mip,
        "algorithm": "ils",
        "operators": registry.weights(),
        "improvement_steps": improvement_steps,
    }
    if operator_stats:
        meta["operators_stats"] = {
            name: {
                "proposals": stats.get("proposals", 0.0),
                "accepted": stats.get("accepted", 0.0),
                "skipped": stats.get("skipped", 0.0),
                "weight": stats.get("weight", 0.0),
                "acceptance_rate": (
                    stats.get("accepted", 0.0) / stats.get("proposals", 1.0)
                    if stats.get("proposals", 0.0)
                    else 0.0
                ),
            }
            for name, stats in operator_stats.items()
        }
    return {"objective": float(best_score), "assignments": assignments, "meta": meta}


__all__ = ["solve_ils"]
