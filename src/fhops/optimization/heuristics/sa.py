"""Simulated annealing heuristic for FHOPS."""

from __future__ import annotations

import math
import random as _random
import time
from collections import deque
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics.common import (
    Schedule,
    build_watch_metadata_from_debug,
    evaluate_candidates,
    evaluate_schedule,
    evaluate_schedule_with_debug,
    generate_neighbors,
    init_greedy_schedule,
    resolve_objective_weight_overrides,
)
from fhops.optimization.heuristics.registry import OperatorRegistry
from fhops.optimization.operational_problem import (
    build_operational_problem,
    override_objective_weights,
)
from fhops.scenario.contract import Problem
from fhops.telemetry import RunTelemetryLogger
from fhops.telemetry.watch import Snapshot, SnapshotSink

__all__ = ["Schedule", "solve_sa"]

AUTO_MOBILISATION_BLOCK_THRESHOLD = 30
AUTO_MOBILISATION_DAY_THRESHOLD = 30
AUTO_MOBILISATION_WEIGHTS = {
    "swap": 0.8,
    "move": 0.8,
    "block_insertion": 0.4,
    "cross_exchange": 0.4,
    "mobilisation_shake": 1.2,
}

AUTO_BATCH_CONFIG: dict[str, int] = {
    "FHOPS Tiny7": 4,
}

AUTO_SHAKE_CONFIG: dict[str, dict[str, float]] = {
    "FHOPS Tiny7": {"threshold": 50.0, "boost_factor": 3.0},
}


def _clone_plan(
    plan: dict[str, dict[tuple[int, str], str | None]],
) -> dict[str, dict[tuple[int, str], str | None]]:
    """Deep-copy a machine/shift assignment plan."""

    return {machine_id: assignments.copy() for machine_id, assignments in plan.items()}


def _assignment_delta(
    baseline: dict[str, dict[tuple[int, str], str | None]],
    candidate: dict[str, dict[tuple[int, str], str | None]],
) -> int:
    """Count slots whose block assignment changed between two plans."""

    diff = 0
    machines = set(baseline.keys()) | set(candidate.keys())
    for machine_id in machines:
        base_slots = baseline.get(machine_id, {})
        cand_slots = candidate.get(machine_id, {})
        slots = set(base_slots.keys()) | set(cand_slots.keys())
        for slot in slots:
            if base_slots.get(slot) != cand_slots.get(slot):
                diff += 1
    return diff


def _should_enable_mobilisation_profile(pb: Problem) -> bool:
    scenario = pb.scenario
    num_blocks = len(getattr(scenario, "blocks", []) or [])
    num_days = getattr(scenario, "num_days", 0) or 0
    return (
        num_blocks >= AUTO_MOBILISATION_BLOCK_THRESHOLD
        or num_days >= AUTO_MOBILISATION_DAY_THRESHOLD
    )


def solve_sa(
    pb: Problem,
    iters: int = 2000,
    seed: int = 42,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
    batch_size: int | None = None,
    max_workers: int | None = None,
    cooling_rate: float = 0.999,
    restart_interval: int | None = None,
    telemetry_log: str | Path | None = None,
    telemetry_context: dict[str, Any] | None = None,
    watch_sink: SnapshotSink | None = None,
    watch_interval: int | None = None,
    watch_metadata: dict[str, str] | None = None,
    watch_debug: bool = False,
    use_local_repairs: bool = False,
    objective_weight_overrides: dict[str, float] | None = None,
    milp_objective: float | None = None,
) -> dict[str, Any]:
    """Solve the scheduling problem with simulated annealing.

    Parameters
    ----------
    pb : fhops.scenario.contract.Problem
        Parsed scenario context describing machines, blocks, and shifts.
    iters : int, default=2000
        Number of annealing iterations. Higher values increase runtime and solution quality.
    seed : int, default=42
        RNG seed used for deterministic runs.
    operators : list[str] | None
        Optional list of operator names to enable (default: all registered operators).
    operator_weights : dict[str, float] | None
        Optional weight overrides for operators (values ``<= 0`` disable an operator).
    batch_size : int | None
        When set, sample up to ``batch_size`` neighbour candidates per iteration.
        ``None`` or ``<= 1`` keeps the sequential single-candidate behaviour.
    max_workers : int | None
        Maximum worker threads for evaluating batched neighbours. ``None``/``<=1`` keeps sequential scoring.
    cooling_rate : float, default=0.999
        Multiplicative cooling factor applied each iteration (0 < rate < 1). Larger values cool more slowly.
    restart_interval : int | None, optional
        Number of consecutive non-accepting iterations before restarting from the greedy seed. ``None`` auto-scales
        to ``max(1000, iters / 5)``.
    telemetry_log : str | pathlib.Path | None
        Optional telemetry JSONL path. When provided, solver progress and final metrics are logged.
    telemetry_context : dict[str, Any] | None
        Additional context merged into telemetry records (scenario metadata, tuner info, etc.).
    watch_sink : SnapshotSink | None, optional
        Optional callback that receives :class:`fhops.telemetry.watch.Snapshot` updates for live
        dashboards. When omitted, no live progress is emitted.
    watch_interval : int | None, optional
        Iteration interval between snapshot emissions. Defaults to ``max(1, iters / 200)`` when a
        sink is provided.
    watch_metadata : dict[str, str] | None
        Additional metadata (e.g., scenario/solver labels) attached to each snapshot.
    watch_debug : bool, default=False
        When ``True`` capture sequencing debug stats for watch snapshots (adds overhead).
    use_local_repairs : bool, default=False
        When ``True`` repairs only the slots touched by a candidate before scoring. The
        final schedule is always re-scored with a full repair before reporting.
    objective_weight_overrides : dict[str, float] | None, optional
        Override scenario objective weights (keys: ``production``, ``mobilisation``, ``transitions``,
        ``landing_surplus``). ``None`` keeps scenario defaults, but Tiny7/Small21 scenarios auto-apply
        a reduced mobilisation weight to encourage exploration.
    milp_objective : float | None, optional
        Reference MILP objective used for gap reporting (best - MILP) in watch/telemetry output.
        ``None`` skips gap metrics.

    Returns
    -------
    dict
        Dictionary with the following keys:

        ``objective`` (float)
            Best objective value achieved during the run (higher is better).
        ``assignments`` (pandas.DataFrame)
            Assignment matrix with columns ``machine_id, block_id, day, shift_id, assigned``.
        ``meta`` (dict[str, Any])
            Telemetry payload including ``operators`` weights, optional ``operators_stats``, and
            bookkeeping such as ``proposals`` or ``telemetry_run_id``.
    """
    rng = _random.Random(seed)
    registry = OperatorRegistry.from_defaults()
    available_names = {name.lower(): name for name in registry.names()}
    auto_profile_applied = False
    if operators:
        desired = {name.lower() for name in operators}
        unknown = desired - set(available_names.keys())
        if unknown:
            raise ValueError(f"Unknown operators requested: {', '.join(sorted(unknown))}")
        disable = {name: 0.0 for lower, name in available_names.items() if lower not in desired}
        if disable:
            registry.configure(disable)
    if operator_weights:
        normalized_weights: dict[str, float] = {}
        for name, weight in operator_weights.items():
            key = name.lower()
            if key not in available_names:
                raise ValueError(f"Unknown operator '{name}' in weights configuration")
            normalized_weights[available_names[key]] = weight
        registry.configure(normalized_weights)
    if not operators and not operator_weights and _should_enable_mobilisation_profile(pb):
        registry.configure(
            {name: AUTO_MOBILISATION_WEIGHTS[name] for name in AUTO_MOBILISATION_WEIGHTS}
        )
        auto_profile_applied = True

    if not 0 < cooling_rate < 1:
        raise ValueError("cooling_rate must be between 0 and 1 (exclusive).")
    restart_interval_value = (
        restart_interval
        if restart_interval and restart_interval > 0
        else max(1000, iters // 5 or 200)
    )

    resolved_weight_overrides = resolve_objective_weight_overrides(pb, objective_weight_overrides)
    if resolved_weight_overrides is not None:
        resolved_weight_overrides = dict(resolved_weight_overrides)

    context_payload = dict(telemetry_context or {})
    step_interval = context_payload.pop("step_interval", 100)
    tuner_meta = context_payload.pop("tuner_meta", None)
    scenario_name = getattr(pb.scenario, "name", None)
    scenario_path = context_payload.pop("scenario_path", None)

    auto_batch_applied = False
    if scenario_name:
        auto_batch = AUTO_BATCH_CONFIG.get(scenario_name)
        if auto_batch and batch_size is None:
            batch_size = auto_batch
            auto_batch_applied = True

    config_snapshot: dict[str, Any] = {
        "iters": iters,
        "batch_size": batch_size,
        "max_workers": max_workers,
        "cooling_rate": cooling_rate,
        "restart_interval": restart_interval_value,
        "operators": registry.weights(),
    }
    if milp_objective is not None:
        config_snapshot["milp_objective"] = float(milp_objective)
    if resolved_weight_overrides:
        config_snapshot["objective_weight_overrides"] = resolved_weight_overrides
    if auto_profile_applied:
        config_snapshot["auto_profile"] = "mobilisation"
    if auto_batch_applied:
        config_snapshot["auto_batch_applied"] = True

    shake_settings = AUTO_SHAKE_CONFIG.get(scenario_name) if scenario_name else None
    mobilisation_shake_default = registry.weights().get("mobilisation_shake", 0.0)
    shake_threshold = (
        float(shake_settings["threshold"])
        if shake_settings and mobilisation_shake_default > 0
        else None
    )
    shake_boost_factor = float(shake_settings["boost_factor"]) if shake_settings else 1.0
    shake_boosted = False
    shake_trigger_count = 0

    if shake_threshold is not None:
        config_snapshot["auto_shake_threshold"] = shake_threshold
        config_snapshot["auto_shake_boost_factor"] = shake_boost_factor

    telemetry_logger: RunTelemetryLogger | None = None
    if telemetry_log:
        log_path = Path(telemetry_log)
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
        telemetry_logger = RunTelemetryLogger(
            log_path=log_path,
            solver="sa",
            scenario=scenario_name,
            scenario_path=scenario_path,
            seed=seed,
            config=config_snapshot,
            context={**scenario_features, **context_payload},
            step_interval=step_interval
            if isinstance(step_interval, int) and step_interval > 0
            else None,
        )

    watch_meta = dict(watch_metadata or {})
    watch_interval_value = watch_interval or max(1, iters // 200 or 1)
    watch_scenario = watch_meta.get("scenario") or scenario_name or "unknown"
    watch_solver = watch_meta.get("solver") or "sa"

    window_size = max(10, min(500, iters // 20 or 10))
    rolling_scores: deque[float] = deque(maxlen=window_size)
    acceptance_window: deque[int] = deque(maxlen=window_size)
    last_watch_best: float | None = None
    workers_total = max_workers if max_workers and max_workers > 1 else None
    current_workers_busy: int | None = workers_total

    ctx = build_operational_problem(pb)
    if resolved_weight_overrides:
        ctx = override_objective_weights(ctx, resolved_weight_overrides)
    debug_capture = bool(watch_debug and watch_sink)
    local_repairs = bool(use_local_repairs)
    objective_weights_snapshot = ctx.bundle.objective_weights.model_dump()

    def _score_schedule(
        schedule: Schedule,
        *,
        capture: bool | None = None,
    ) -> tuple[float, dict[str, Any] | None]:
        """Evaluate a schedule and optionally capture sequencing debug stats."""

        flag = debug_capture if capture is None else capture
        if flag:
            return evaluate_schedule_with_debug(
                pb,
                schedule,
                ctx,
                capture_debug=True,
                limit_repairs_to_dirty=local_repairs,
            )
        return evaluate_schedule(
            pb,
            schedule,
            ctx,
            limit_repairs_to_dirty=local_repairs,
        ), None

    with telemetry_logger if telemetry_logger else nullcontext() as run_logger:
        current = init_greedy_schedule(pb, ctx)
        current_score, current_debug_stats = _score_schedule(current)
        best = current
        best_score = current_score
        best_debug_stats = dict(current_debug_stats) if current_debug_stats else None
        initial_plan = _clone_plan(current.plan)
        assignment_slots_total = sum(len(assignments) for assignments in initial_plan.values())
        best_assignment_delta = 0

        temperature0 = max(1.0, best_score / 10.0)
        temperature = temperature0
        initial_score = current_score
        proposals = 0
        accepted_moves = 0
        restarts = 0
        stalled_steps = 0
        operator_stats: dict[str, dict[str, float]] = {}
        run_start = time.perf_counter()
        for step in range(1, iters + 1):
            accepted = False
            candidates = generate_neighbors(
                pb,
                current,
                registry,
                rng,
                operator_stats,
                ctx,
                batch_size=batch_size,
            )
            evaluations = evaluate_candidates(
                pb,
                candidates,
                ctx,
                max_workers=max_workers if batch_size and batch_size > 1 else None,
                limit_repairs_to_dirty=local_repairs,
            )
            if workers_total:
                current_workers_busy = min(workers_total, len(evaluations)) if evaluations else 0
            for neighbor, neighbor_score in evaluations:
                proposals += 1
                delta = neighbor_score - current_score
                if delta >= 0 or rng.random() < math.exp(delta / max(temperature, 1e-6)):
                    current = neighbor
                    current_score = neighbor_score
                    accepted = True
                    accepted_moves += 1
                    if debug_capture:
                        current_score, current_debug_stats = _score_schedule(current, capture=True)
                    else:
                        current_debug_stats = None
                    break
            if current_score > best_score:
                best, best_score = current, current_score
                best_debug_stats = dict(current_debug_stats) if current_debug_stats else None
                best_assignment_delta = _assignment_delta(initial_plan, best.plan)
            temperature = max(temperature * cooling_rate, 1e-6)
            if run_logger and telemetry_logger and telemetry_logger.step_interval:
                if step == 1 or step == iters or (step % telemetry_logger.step_interval == 0):
                    acceptance_rate_log = (accepted_moves / proposals) if proposals else 0.0
                    run_logger.log_step(
                        step=step,
                        objective=float(current_score),
                        best_objective=float(best_score),
                        temperature=float(temperature),
                        acceptance_rate=acceptance_rate_log,
                        proposals=proposals,
                        accepted_moves=accepted_moves,
                    )
            if accepted:
                stalled_steps = 0
            else:
                stalled_steps += 1

            if shake_threshold is not None:
                if stalled_steps >= shake_threshold and not shake_boosted:
                    boost_value = mobilisation_shake_default * shake_boost_factor
                    registry.configure({"mobilisation_shake": boost_value})
                    shake_boosted = True
                    shake_trigger_count += 1
                elif shake_boosted and stalled_steps == 0:
                    registry.configure({"mobilisation_shake": mobilisation_shake_default})
                    shake_boosted = False

            if stalled_steps >= restart_interval_value:
                current = init_greedy_schedule(pb, ctx)
                current_score, current_debug_stats = _score_schedule(current)
                restarts += 1
                stalled_steps = 0
                temperature = temperature0

            rolling_scores.append(float(current_score))
            acceptance_window.append(1 if accepted else 0)

            if watch_sink and (step == 1 or step == iters or (step % watch_interval_value == 0)):
                acceptance_rate_watch = (accepted_moves / proposals) if proposals else None
                rolling_mean = (
                    float(sum(rolling_scores) / len(rolling_scores))
                    if rolling_scores
                    else float(current_score)
                )
                window_acceptance = (
                    float(sum(acceptance_window) / len(acceptance_window))
                    if acceptance_window
                    else None
                )
                delta_objective = (
                    float(best_score - last_watch_best) if last_watch_best is not None else 0.0
                )
                last_watch_best = float(best_score)
                metadata = dict(watch_meta)
                if debug_capture:
                    metadata.update(build_watch_metadata_from_debug(current_debug_stats))
                elif getattr(current, "watch_stats", None):
                    metadata.update(build_watch_metadata_from_debug(current.watch_stats))
                metadata.setdefault("greedy_objective", f"{initial_score:.3f}")
                metadata.setdefault("obj_delta_vs_initial", f"{best_score - initial_score:.3f}")
                metadata.setdefault("assignment_delta_slots", str(best_assignment_delta))
                if milp_objective is not None:
                    metadata["milp_objective"] = f"{milp_objective:.3f}"
                    metadata["milp_gap"] = f"{best_score - milp_objective:.3f}"
                watch_sink(
                    Snapshot(
                        scenario=watch_scenario,
                        solver=watch_solver,
                        iteration=step,
                        max_iterations=iters,
                        objective=float(best_score),
                        best_gap=None,
                        runtime_seconds=time.perf_counter() - run_start,
                        acceptance_rate=acceptance_rate_watch,
                        restarts=restarts,
                        workers_busy=current_workers_busy,
                        workers_total=workers_total,
                        current_objective=float(current_score),
                        rolling_objective=rolling_mean,
                        temperature=float(temperature),
                        acceptance_rate_window=window_acceptance,
                        delta_objective=delta_objective,
                        metadata=metadata,
                    )
                )

        # Re-score the best schedule with a full repair pass for final reporting.
        if local_repairs:
            if debug_capture:
                best_score, best_debug_stats = evaluate_schedule_with_debug(
                    pb,
                    best,
                    ctx,
                    capture_debug=True,
                    limit_repairs_to_dirty=False,
                )
            else:
                best_score = evaluate_schedule(pb, best, ctx, limit_repairs_to_dirty=False)
            current_score = evaluate_schedule(pb, current, ctx, limit_repairs_to_dirty=False)

        rows: list[dict[str, str | int]] = []
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
        assignment_columns = ["machine_id", "block_id", "day", "shift_id", "assigned"]
        assignments = pd.DataFrame(rows, columns=assignment_columns)
        if not assignments.empty:
            assignments = assignments.sort_values(["day", "shift_id", "machine_id", "block_id"])
        if watch_sink:
            acceptance_rate_watch = (accepted_moves / proposals) if proposals else None
            rolling_mean = (
                float(sum(rolling_scores) / len(rolling_scores))
                if rolling_scores
                else float(current_score)
            )
            window_acceptance = (
                float(sum(acceptance_window) / len(acceptance_window))
                if acceptance_window
                else None
            )
            delta_objective = (
                float(best_score - last_watch_best) if last_watch_best is not None else 0.0
            )
            last_watch_best = float(best_score)
            metadata = dict(watch_meta)
            if debug_capture:
                metadata.update(build_watch_metadata_from_debug(best_debug_stats))
            elif getattr(best, "watch_stats", None):
                metadata.update(build_watch_metadata_from_debug(best.watch_stats))
            metadata.setdefault("greedy_objective", f"{initial_score:.3f}")
            metadata.setdefault("obj_delta_vs_initial", f"{best_score - initial_score:.3f}")
            metadata.setdefault("assignment_delta_slots", str(best_assignment_delta))
            if milp_objective is not None:
                metadata["milp_objective"] = f"{milp_objective:.3f}"
                metadata["milp_gap"] = f"{best_score - milp_objective:.3f}"
            watch_sink(
                Snapshot(
                    scenario=watch_scenario,
                    solver=watch_solver,
                    iteration=iters,
                    max_iterations=iters,
                    objective=float(best_score),
                    best_gap=None,
                    runtime_seconds=time.perf_counter() - run_start,
                    acceptance_rate=acceptance_rate_watch,
                    restarts=restarts,
                    workers_busy=current_workers_busy,
                    workers_total=workers_total,
                    current_objective=float(current_score),
                    rolling_objective=rolling_mean,
                    temperature=float(temperature),
                    acceptance_rate_window=window_acceptance,
                    delta_objective=delta_objective,
                    metadata=metadata,
                )
            )
        if shake_boosted and shake_threshold is not None:
            registry.configure({"mobilisation_shake": mobilisation_shake_default})
            shake_boosted = False

        meta = {
            "initial_score": float(initial_score),
            "best_score": float(best_score),
            "proposals": proposals,
            "accepted_moves": accepted_moves,
            "acceptance_rate": (accepted_moves / proposals) if proposals else 0.0,
            "restarts": restarts,
            "iterations": iters,
            "temperature0": float(temperature0),
            "cooling_rate": float(cooling_rate),
            "restart_interval": int(restart_interval_value),
            "operators": registry.weights(),
            "batch_size": batch_size,
            "max_workers": max_workers,
            "auto_batch_applied": auto_batch_applied,
            "auto_shake_triggers": shake_trigger_count if shake_threshold is not None else 0,
        }
        if milp_objective is not None:
            meta["milp_objective"] = float(milp_objective)
            meta["milp_gap"] = float(best_score - milp_objective)
        if resolved_weight_overrides:
            meta["objective_weight_overrides"] = resolved_weight_overrides
        meta["objective_weights"] = objective_weights_snapshot
        meta.update(
            {
                "greedy_objective": float(initial_score),
                "best_delta_vs_greedy": float(best_score - initial_score),
                "assignment_delta_slots": int(best_assignment_delta),
                "assignment_total_slots": int(assignment_slots_total),
            }
        )
        if operator_stats:
            meta["operators_stats"] = {
                name: {
                    "proposals": stats.get("proposals", 0.0),
                    "accepted": stats.get("accepted", 0.0),
                    "skipped": stats.get("skipped", 0.0),
                    "weight": stats.get("weight", 0.0),
                    "acceptance_rate": (stats.get("accepted", 0.0) / stats.get("proposals", 1.0))
                    if stats.get("proposals", 0.0)
                    else 0.0,
                }
                for name, stats in operator_stats.items()
            }
        kpi_result = compute_kpis(pb, assignments)
        kpi_totals = kpi_result.to_dict()
        meta["kpi_totals"] = {
            key: (float(value) if isinstance(value, int | float) else value)
            for key, value in kpi_totals.items()
        }
        if run_logger and telemetry_logger:
            numeric_kpis = {
                key: float(value)
                for key, value in kpi_totals.items()
                if isinstance(value, int | float)
            }
            if tuner_meta is not None:
                progress = tuner_meta.setdefault("progress", {})
                progress.setdefault("best_objective", float(best_score))
                progress.setdefault("iterations", iters)
            run_logger.finalize(
                status="ok",
                metrics={
                    "objective": float(best_score),
                    "initial_score": float(initial_score),
                    "objective_delta_vs_initial": float(best_score - initial_score),
                    "acceptance_rate": meta["acceptance_rate"],
                    **(
                        {
                            "milp_objective": float(milp_objective),
                            "milp_gap": float(best_score - milp_objective),
                        }
                        if milp_objective is not None
                        else {}
                    ),
                    **numeric_kpis,
                },
                extra={
                    "iterations": iters,
                    "restarts": restarts,
                    "proposals": proposals,
                    "accepted_moves": accepted_moves,
                    "temperature0": float(temperature0),
                    "operators": registry.weights(),
                    "assignment_delta_slots": int(best_assignment_delta),
                },
                kpis=kpi_totals,
                tuner_meta=tuner_meta,
            )
            meta["telemetry_run_id"] = telemetry_logger.run_id
            if telemetry_logger.steps_path:
                meta["telemetry_steps_path"] = str(telemetry_logger.steps_path)
            meta["telemetry_log_path"] = str(telemetry_logger.log_path)

    return {
        "objective": float(best_score),
        "assignments": assignments,
        "meta": meta,
        "schedule": best,
    }
