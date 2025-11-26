"""Iterated Local Search / hybrid heuristic leveraging the operator registry."""

from __future__ import annotations

import random as _random
import time
from collections import deque
from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast

import pandas as pd

from fhops.evaluation import compute_kpis
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
from fhops.telemetry import RunTelemetryLogger
from fhops.telemetry.watch import Snapshot, SnapshotSink


def _assignments_to_schedule(pb: Problem, assignments: pd.DataFrame) -> Schedule:
    """Convert an assignments DataFrame into the internal Schedule plan structure."""
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
    """Apply a series of random operator moves to escape local optima."""
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
    """Run local search until no improving neighbour is found."""
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
    telemetry_log: str | Path | None = None,
    telemetry_context: dict[str, Any] | None = None,
    watch_sink: SnapshotSink | None = None,
    watch_interval: int | None = None,
    watch_metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run Iterated Local Search (optionally with MIP warm starts).

    Parameters
    ----------
    pb : fhops.scenario.contract.Problem
        Parsed problem definition containing the schedule context.
    iters : int, default=50
        Number of ILS outer iterations (local search + perturbation cycles).
    seed : int, default=42
        Seed used for deterministic RNG behaviour.
    operators : list[str] | None
        Optional list of operator names to enable. Defaults to the registry defaults.
    operator_weights : dict[str, float] | None
        Optional weight overrides for registered operators.
    batch_size : int | None
        Number of neighbours sampled per local search step (``None`` keeps sequential sampling).
    max_workers : int | None
        Worker pool size for evaluating batched neighbours (``None`` keeps sequential evaluation).
    perturbation_strength : int, default=3
        Count of perturbation steps applied when diversification is required.
    stall_limit : int, default=10
        Non-improving iterations before triggering perturbation or hybrid restart.
    hybrid_use_mip : bool, default=False
        When ``True`` attempt a time-boxed MIP warm start once stalls exceed the limit.
    hybrid_mip_time_limit : int, default=60
        Time limit (seconds) forwarded to the hybrid MIP warm start.
    telemetry_log : str | pathlib.Path | None
        Optional telemetry JSONL log capturing run metadata and (when configured) step logs.
    telemetry_context : dict[str, Any] | None
        Extra context appended to telemetry events (scenario info, tuner metadata, etc.).
    watch_sink : SnapshotSink | None, optional
        Optional callback that consumes live :class:`fhops.telemetry.watch.Snapshot` updates for
        dashboards.
    watch_interval : int | None, optional
        Emit snapshots every ``watch_interval`` outer iterations (defaults to ``iters / 20``).
    watch_metadata : dict[str, str] | None
        Extra metadata (scenario/solver labels) attached to snapshot payloads.

    Returns
    -------
    dict
        Dictionary mirroring :func:`solve_sa` with ``objective``, ``assignments`` DataFrame, and a
        ``meta`` payload describing operator stats, iterations, and telemetry identifiers.
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

    config_snapshot = {
        "iters": iters,
        "batch_size": batch_size,
        "max_workers": max_workers,
        "perturbation_strength": perturbation_strength,
        "stall_limit": stall_limit,
        "hybrid_use_mip": hybrid_use_mip,
        "hybrid_mip_time_limit": hybrid_mip_time_limit,
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
            solver="ils",
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
    watch_solver = watch_meta.get("solver") or "ils"
    window_size = max(10, min(200, iters // 10 or 10))
    rolling_scores: deque[float] = deque(maxlen=window_size)
    improvement_window: deque[int] = deque(maxlen=window_size)
    last_watch_best: float | None = None

    with telemetry_logger if telemetry_logger else nullcontext() as run_logger:
        current = _init_greedy(pb)
        current_score = _evaluate(pb, current)
        best = current
        best_score = current_score
        initial_score = current_score
        rolling_scores.append(float(current_score))

        stalls = 0
        perturbations = 0
        restarts = 0
        improvement_steps = 0
        operator_stats: dict[str, dict[str, float]] = {}
        run_start = time.perf_counter()

        def emit_snapshot(iteration: int) -> None:
            nonlocal last_watch_best
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
            delta_objective = (
                float(best_score - last_watch_best) if last_watch_best is not None else 0.0
            )
            last_watch_best = float(best_score)
            metadata = {
                **watch_meta,
                "stalls": str(stalls),
                "perturbations": str(perturbations),
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
                    acceptance_rate=None,
                    restarts=restarts,
                    current_objective=float(current_score),
                    rolling_objective=rolling_mean,
                    temperature=None,
                    acceptance_rate_window=window_acceptance,
                    delta_objective=delta_objective,
                    metadata=metadata,
                )
            )

        total_iterations = max(1, iters)
        for iteration in range(1, total_iterations + 1):
            current, current_score, improved, steps = _local_search(
                pb, current, registry, rng, batch_arg, worker_arg, operator_stats
            )
            improvement_steps += steps
            rolling_scores.append(float(current_score))
            best_improved = False
            if current_score > best_score:
                best, best_score = current, current_score
                stalls = 0
                best_improved = True
            else:
                stalls += 1
            improvement_window.append(1 if best_improved else 0)

            if run_logger and telemetry_logger and telemetry_logger.step_interval:
                if (
                    iteration == 1
                    or iteration == total_iterations
                    or iteration % telemetry_logger.step_interval == 0
                ):
                    run_logger.log_step(
                        step=iteration,
                        objective=float(current_score),
                        best_objective=float(best_score),
                        temperature=None,
                        acceptance_rate=None,
                        proposals=int(steps),
                        accepted_moves=int(steps if improved else 0),
                    )

            if watch_sink and (
                iteration == 1
                or iteration == total_iterations
                or (iteration % watch_interval_value == 0)
            ):
                emit_snapshot(iteration)

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
                stalls = 0
                perturbations += 1
            else:
                current = _perturb_schedule(
                    pb, current, registry, rng, perturbation_strength, operator_stats
                )
                current_score = _evaluate(pb, current)
                perturbations += 1
                rolling_scores.append(float(current_score))
                improvement_window.append(0)

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
                    "perturbations": perturbations,
                    "restarts": restarts,
                    "stall_limit": stall_limit,
                    "perturbation_strength": perturbation_strength,
                    "hybrid_used": hybrid_use_mip,
                },
                kpis=kpi_totals,
                tuner_meta=tuner_meta,
            )
            meta["telemetry_run_id"] = telemetry_logger.run_id
            meta["telemetry_log_path"] = str(telemetry_logger.log_path)
            if telemetry_logger.steps_path:
                meta["telemetry_steps_path"] = str(telemetry_logger.steps_path)

    return {"objective": float(best_score), "assignments": assignments, "meta": meta}


__all__ = ["solve_ils"]
