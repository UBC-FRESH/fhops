"""Tabu Search heuristic built on top of the operator registry."""

from __future__ import annotations

import random as _random
from collections import deque
from dataclasses import dataclass
from typing import Any

import pandas as pd

from fhops.optimization.heuristics.registry import OperatorRegistry
from fhops.optimization.heuristics.sa import (
    _evaluate,
    _evaluate_candidates,
    _init_greedy,
    _neighbors,
)
from fhops.scenario.contract import Problem


@dataclass(slots=True)
class TabuConfig:
    tenure: int
    stall_limit: int


def _diff_moves(current_plan: dict[str, dict[tuple[int, str], str | None]], candidate_plan: dict[str, dict[tuple[int, str], str | None]]) -> tuple[tuple[str, int, str, str | None, str | None], ...]:
    moves: list[tuple[str, int, str, str | None, str | None]] = []
    for machine_id, assignments in candidate_plan.items():
        current_assignments = current_plan.get(machine_id, {})
        for (day, shift_id), new_block in assignments.items():
            old_block = current_assignments.get((day, shift_id))
            if old_block != new_block:
                moves.append((machine_id, day, shift_id, old_block, new_block))
    return tuple(sorted(moves))


def solve_tabu(
    pb: Problem,
    *,
    iters: int = 2000,
    seed: int = 42,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
    batch_size: int | None = None,
    max_workers: int | None = None,
    tabu_tenure: int | None = None,
    stall_limit: int = 200,
) -> dict[str, Any]:
    """Run Tabu Search using the shared operator registry."""

    rng = _random.Random(seed)
    registry = OperatorRegistry.from_defaults()
    available = {name.lower(): name for name in registry.names()}
    if operators:
        requested = {name.lower() for name in operators}
        unknown = requested - set(available.keys())
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

    current = _init_greedy(pb)
    current_score = _evaluate(pb, current)
    initial_score = current_score
    best = current
    best_score = current_score

    tenure = tabu_tenure if tabu_tenure is not None else max(10, len(pb.scenario.machines))
    tabu_queue: deque[tuple[tuple[str, int, str, str | None, str | None], ...]] = deque(maxlen=tenure)
    tabu_set: set[tuple[tuple[str, int, str, str | None, str | None], ...]] = set()

    batch_arg = batch_size if batch_size and batch_size > 0 else None
    worker_arg = max_workers if max_workers and max_workers > 1 else None

    proposals = 0
    improvements = 0
    stalls = 0
    operator_stats: dict[str, dict[str, float]] = {}

    for step in range(1, iters + 1):
        candidates = _neighbors(
            pb,
            current,
            registry,
            rng,
            operator_stats,
            batch_size=batch_arg,
        )
        evaluations = _evaluate_candidates(pb, candidates, worker_arg)
        if not evaluations:
            break

        best_candidate_tuple: tuple[Any, ...] | None = None
        for candidate, score in sorted(evaluations, key=lambda item: item[1], reverse=True):
            proposals += 1
            move_sig = _diff_moves(current.plan, candidate.plan)
            is_tabu = move_sig in tabu_set
            aspiration = score > best_score
            if not is_tabu or aspiration:
                best_candidate_tuple = (candidate, score, move_sig)
                break

        if best_candidate_tuple is None:
            break

        candidate, score, move_sig = best_candidate_tuple
        current = candidate
        current_score = score

        if move_sig in tabu_set:
            tabu_set.discard(move_sig)
            try:
                tabu_queue.remove(move_sig)
            except ValueError:
                pass
        if len(tabu_queue) >= tenure:
            expired = tabu_queue.popleft()
            tabu_set.discard(expired)
        tabu_queue.append(move_sig)
        tabu_set.add(move_sig)

        if current_score > best_score:
            best = current
            best_score = current_score
            stalls = 0
            improvements += 1
        else:
            stalls += 1
        if stalls >= stall_limit:
            break

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
        "proposals": proposals,
        "improvements": improvements,
        "stall_limit": stall_limit,
        "tabu_tenure": tenure,
        "operators": registry.weights(),
        "algorithm": "tabu",
    }
    if operator_stats:
        meta["operators_stats"] = operator_stats
    return {"objective": float(best_score), "assignments": assignments, "meta": meta}


__all__ = ["solve_tabu", "TabuConfig"]
