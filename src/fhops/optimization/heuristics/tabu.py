"""Tabu Search heuristic built on top of the operator registry."""

from __future__ import annotations

import random as _random
import time
from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics.common import (
    evaluate_candidates,
    evaluate_schedule,
    generate_neighbors,
    init_greedy_schedule,
)
from fhops.optimization.heuristics.registry import OperatorRegistry
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.telemetry import RunTelemetryLogger
from fhops.telemetry.watch import Snapshot, SnapshotSink

TABU_DEFAULT_OPERATOR_WEIGHTS: dict[str, float] = {
    "swap": 1.0,
    "move": 1.0,
    "block_insertion": 0.6,
    "cross_exchange": 0.6,
    "mobilisation_shake": 0.4,
}


@dataclass(slots=True)
class TabuConfig:
    """Runtime Tabu settings (tenure length and stall tolerance)."""

    tenure: int
    stall_limit: int


def _diff_moves(
    current_plan: dict[str, dict[tuple[int, str], str | None]],
    candidate_plan: dict[str, dict[tuple[int, str], str | None]],
) -> tuple[tuple[str, int, str, str | None, str | None], ...]:
    """Return a canonical list of move tuples describing differences between two plans."""
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
    stall_limit: int = 1_000_000,
    telemetry_log: str | Path | None = None,
    telemetry_context: dict[str, Any] | None = None,
    watch_sink: SnapshotSink | None = None,
    watch_interval: int | None = None,
    watch_metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run Tabu Search using the shared operator registry.

    Parameters
    ----------
    pb : fhops.scenario.contract.Problem
        Parsed scenario context describing machines, blocks, and shifts.
    iters : int, default=2000
        Number of Tabu Search iterations to execute.
    seed : int, default=42
        RNG seed that controls neighbourhood sampling and diversification.
    operators : list[str] | None
        Optional subset of operator names to enable (defaults to the registry defaults).
    operator_weights : dict[str, float] | None
        Weight overrides for operators. Values ``<= 0`` disable the operator.
    batch_size : int | None
        Number of neighbour candidates sampled per iteration (``None`` keeps sequential sampling).
    max_workers : int | None
        Worker threads for evaluating batched neighbours (``None`` keeps sequential evaluation).
    tabu_tenure : int | None
        Explicit tenure length. ``None`` auto-sizes the tabu queue based on machine count.
    stall_limit : int, default=1_000_000
        Max consecutive non-improving iterations before giving up.
    telemetry_log : str | pathlib.Path | None
        Optional telemetry JSONL path for recording solver progress and metrics.
    telemetry_context : dict[str, Any] | None
        Additional context appended to telemetry entries (scenario features, tuner metadata, etc.).
    watch_sink : SnapshotSink | None, optional
        Optional callback receiving live :class:`fhops.telemetry.watch.Snapshot` updates.
    watch_interval : int | None, optional
        Emit watch updates every ``watch_interval`` iterations (defaults to ``iters / 20``).
    watch_metadata : dict[str, str] | None
        Metadata merged into each snapshot (scenario/solver labels, run IDs, etc.).

    Returns
    -------
    dict
        Dictionary with ``objective`` (float), ``assignments`` (pandas.DataFrame), and ``meta`` with
        operator stats, acceptance counters, and optional ``telemetry_run_id``—matching the contract
        exposed by :func:`solve_sa` / :func:`solve_ils`.
    """

    rng = _random.Random(seed)
    registry = OperatorRegistry.from_defaults()
    available = {name.lower(): name for name in registry.names()}
    default_operator_weights = {
        available[name]: weight
        for name, weight in TABU_DEFAULT_OPERATOR_WEIGHTS.items()
        if name in available
    }
    if default_operator_weights:
        registry.configure(default_operator_weights)
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

    config_snapshot = {
        "iters": iters,
        "batch_size": batch_size,
        "max_workers": max_workers,
        "tabu_tenure": tabu_tenure,
        "stall_limit": stall_limit,
        "operators": registry.weights(),
    }
    context_payload = dict(telemetry_context or {})
    scenario = pb.scenario
    timeline = getattr(scenario, "timeline", None)
    scenario_features = {
        "num_days": getattr(scenario, "num_days", None),
        "num_blocks": len(getattr(scenario, "blocks", []) or []),
        "num_machines": len(getattr(scenario, "machines", []) or []),
        "num_landings": len(getattr(scenario, "landings", []) or []),
        "num_shift_calendar_entries": len(getattr(scenario, "shift_calendar", []) or []),
        "num_timeline_shifts": len(getattr(timeline, "shifts", []) or []),
    }
    context_payload.setdefault("scenario_features", scenario_features)
    step_interval = context_payload.pop("step_interval", 25)
    tuner_meta = context_payload.pop("tuner_meta", None)
    scenario_name = getattr(pb.scenario, "name", None)
    scenario_path = context_payload.pop("scenario_path", None)

    telemetry_logger: RunTelemetryLogger | None = None
    if telemetry_log:
        log_path = Path(telemetry_log)
        telemetry_context = dict(context_payload)
        telemetry_context.update(scenario_features)
        telemetry_logger = RunTelemetryLogger(
            log_path=log_path,
            solver="tabu",
            scenario=scenario_name,
            scenario_path=scenario_path,
            seed=seed,
            config=config_snapshot,
            context=telemetry_context,
            step_interval=step_interval
            if isinstance(step_interval, int) and step_interval > 0
            else None,
        )

    watch_meta = dict(watch_metadata or {})
    watch_interval_value = watch_interval or max(1, iters // 20 or 1)
    watch_scenario = watch_meta.get("scenario") or scenario_name or "unknown"
    watch_solver = watch_meta.get("solver") or "tabu"
    window_size = max(10, min(200, iters // 10 or 10))
    rolling_scores: deque[float] = deque(maxlen=window_size)
    improvement_window: deque[int] = deque(maxlen=window_size)
    last_watch_best: float | None = None
    last_emitted_step: int | None = None

    ctx = build_operational_problem(pb)

    with telemetry_logger if telemetry_logger else nullcontext() as run_logger:
        current = init_greedy_schedule(pb, ctx)
        current_score = evaluate_schedule(pb, current, ctx)
        initial_score = current_score
        best = current
        best_score = current_score
        rolling_scores.append(float(current_score))

        tenure = tabu_tenure if tabu_tenure is not None else max(10, len(pb.scenario.machines))
        tabu_queue: deque[tuple[tuple[str, int, str, str | None, str | None], ...]] = deque(
            maxlen=tenure
        )
        tabu_set: set[tuple[tuple[str, int, str, str | None, str | None], ...]] = set()

        batch_arg = batch_size if batch_size and batch_size > 0 else None
        worker_arg = max_workers if max_workers and max_workers > 1 else None

        proposals = 0
        improvements = 0
        stalls = 0
        restarts = 0
        operator_stats: dict[str, dict[str, float]] = {}
        run_start = time.perf_counter()
        workers_total = worker_arg if worker_arg and worker_arg > 1 else None
        current_workers_busy: int | None = workers_total

        def emit_snapshot(iteration: int) -> None:
            nonlocal last_watch_best, last_emitted_step
            if not watch_sink:
                return
            rolling_mean = (
                float(sum(rolling_scores) / len(rolling_scores))
                if rolling_scores
                else float(current_score)
            )
            window_acceptance = (
                float(sum(improvement_window) / len(improvement_window))
                if improvement_window
                else None
            )
            acceptance_rate = (improvements / proposals) if proposals else None
            delta_objective = (
                float(best_score - last_watch_best) if last_watch_best is not None else 0.0
            )
            last_watch_best = float(best_score)
            last_emitted_step = iteration
            metadata = {
                **watch_meta,
                "iterations_since_improvement": str(stalls),
                "tabu_tenure": str(tenure),
                "restarts": str(restarts),
            }
            watch_sink(
                Snapshot(
                    scenario=watch_scenario,
                    solver=watch_solver,
                    iteration=iteration,
                    max_iterations=iters,
                    objective=float(best_score),
                    best_gap=None,
                    runtime_seconds=time.perf_counter() - run_start,
                    acceptance_rate=acceptance_rate,
                    restarts=restarts,
                    workers_busy=current_workers_busy,
                    workers_total=workers_total,
                    current_objective=float(current_score),
                    rolling_objective=rolling_mean,
                    temperature=None,
                    acceptance_rate_window=window_acceptance,
                    delta_objective=delta_objective,
                    metadata=metadata,
                )
            )

        last_iteration = 0
        for step in range(1, iters + 1):
            candidates = generate_neighbors(
                pb,
                current,
                registry,
                rng,
                operator_stats,
                ctx,
                batch_size=batch_arg,
            )
            evaluations = evaluate_candidates(pb, candidates, ctx, worker_arg)
            if not evaluations:
                break
            if workers_total:
                current_workers_busy = min(workers_total, len(evaluations)) if evaluations else 0

            best_candidate_tuple: tuple[Any, ...] | None = None
            fallback_candidate_tuple: tuple[Any, ...] | None = None
            for candidate, score in sorted(evaluations, key=lambda item: item[1], reverse=True):
                proposals += 1
                move_sig = _diff_moves(current.plan, candidate.plan)
                is_tabu = move_sig in tabu_set
                aspiration = score > best_score
                if not is_tabu or aspiration:
                    best_candidate_tuple = (candidate, score, move_sig)
                    break
                if fallback_candidate_tuple is None:
                    fallback_candidate_tuple = (candidate, score, move_sig)

            if best_candidate_tuple is None:
                if fallback_candidate_tuple is None:
                    break
                # Forced diversification: relax tabu constraint by expiring the oldest entry.
                if len(tabu_queue) >= tenure:
                    expired = tabu_queue.popleft()
                    tabu_set.discard(expired)
                best_candidate_tuple = fallback_candidate_tuple

            candidate, score, move_sig = best_candidate_tuple
            current = candidate
            current_score = score
            rolling_scores.append(float(current_score))

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

            best_improved = False
            if current_score > best_score:
                best = current
                best_score = current_score
                stalls = 0
                improvements += 1
                best_improved = True
            else:
                stalls += 1
            improvement_window.append(1 if best_improved else 0)
            last_iteration = step

            if run_logger and telemetry_logger and telemetry_logger.step_interval:
                if step == 1 or step == iters or step % telemetry_logger.step_interval == 0:
                    acceptance_rate = (improvements / proposals) if proposals else None
                    run_logger.log_step(
                        step=step,
                        objective=float(current_score),
                        best_objective=float(best_score),
                        temperature=None,
                        acceptance_rate=acceptance_rate,
                        proposals=proposals,
                        accepted_moves=improvements,
                    )

            if watch_sink and (step == 1 or step == iters or (step % watch_interval_value == 0)):
                emit_snapshot(step)

            if stalls >= stall_limit:
                restarts += 1
                stalls = 0
                current = best
                current_score = best_score
                tabu_queue.clear()
                tabu_set.clear()
                continue

        if watch_sink and last_iteration and last_emitted_step != last_iteration:
            emit_snapshot(last_iteration)

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
            "restarts": restarts,
            "operators": registry.weights(),
            "algorithm": "tabu",
        }
        if operator_stats:
            meta["operators_stats"] = operator_stats

        kpi_result = compute_kpis(pb, assignments)
        kpi_totals = kpi_result.to_dict()
        meta["kpi_totals"] = {
            key: (float(value) if isinstance(value, int | float) else value)
            for key, value in kpi_totals.items()
        }

        if tuner_meta is not None:
            progress = tuner_meta.setdefault("progress", {})
            progress.setdefault("best_objective", float(best_score))
            progress.setdefault("iterations", iters)
        if run_logger and telemetry_logger:
            numeric_kpis = {
                key: float(value)
                for key, value in kpi_totals.items()
                if isinstance(value, int | float)
            }
            run_logger.finalize(
                status="ok",
                metrics={
                    "objective": float(best_score),
                    "initial_score": float(initial_score),
                    **numeric_kpis,
                },
                extra={
                    "iterations": iters,
                    "proposals": proposals,
                    "improvements": improvements,
                    "stall_limit": stall_limit,
                    "tabu_tenure": tenure,
                },
                kpis=kpi_totals,
                tuner_meta=tuner_meta,
            )
            meta["telemetry_run_id"] = telemetry_logger.run_id
            meta["telemetry_log_path"] = str(telemetry_logger.log_path)
            if telemetry_logger.steps_path:
                meta["telemetry_steps_path"] = str(telemetry_logger.steps_path)

    return {"objective": float(best_score), "assignments": assignments, "meta": meta}


__all__ = ["solve_tabu", "TabuConfig"]
