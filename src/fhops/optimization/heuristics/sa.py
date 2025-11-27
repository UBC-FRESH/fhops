"""Simulated annealing heuristic for FHOPS."""

from __future__ import annotations

import math
import random as _random
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics.registry import OperatorContext, OperatorRegistry
from fhops.optimization.operational_problem import (
    OperationalProblem,
    build_operational_problem,
)
from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import MachineMobilisation
from fhops.telemetry import RunTelemetryLogger
from fhops.telemetry.watch import Snapshot, SnapshotSink

BLOCK_COMPLETION_EPS = 1e-6
PARTIAL_PRODUCTION_FRACTION = 0.1
LEFTOVER_PENALTY_FACTOR = 5.0


__all__ = ["Schedule", "solve_sa"]


@dataclass(slots=True)
class Schedule:
    """Machine assignment plan keyed by machine/(day, shift_id)."""

    plan: dict[str, dict[tuple[int, str], str | None]]


def _init_greedy(pb: Problem, ctx: OperationalProblem) -> Schedule:
    """Construct an initial Schedule by greedily filling shifts with best-rate blocks."""

    sc = pb.scenario
    bundle = ctx.bundle
    remaining = dict(bundle.work_required)
    rate = bundle.production_rates
    shift_availability = bundle.availability_shift
    availability = bundle.availability_day
    windows = bundle.windows
    allowed_roles = ctx.allowed_roles
    machine_roles = bundle.machine_roles
    blackout = ctx.blackout_shifts
    locked = ctx.locked_assignments

    shifts = sorted(pb.shifts, key=lambda s: (s.day, s.shift_id))
    shift_keys = [(shift.day, shift.shift_id) for shift in shifts]
    plan: dict[str, dict[tuple[int, str], str | None]] = {
        machine.id: {(day, shift_id): None for day, shift_id in shift_keys}
        for machine in sc.machines
    }

    def assign(machine_id: str, day: int, shift_id: str, block_id: str | None) -> None:
        plan[machine_id][(day, shift_id)] = block_id
        if block_id is None:
            return
        production = min(rate.get((machine_id, block_id), 0.0), remaining[block_id])
        remaining[block_id] = max(0.0, remaining[block_id] - production)

    def best_slot_for(block_id: str) -> tuple[str, int, str] | None:
        earliest, latest = windows[block_id]
        best_slot: tuple[str, int, str] | None = None
        best_rate = 0.0
        allowed = allowed_roles.get(block_id)
        for machine in sc.machines:
            role = machine_roles.get(machine.id)
            if allowed is not None and role is not None and role not in allowed:
                continue
            for shift in shifts:
                day, shift_id = shift.day, shift.shift_id
                if day < earliest or day > latest:
                    continue
                if plan[machine.id][(day, shift_id)] is not None:
                    continue
                if shift_availability.get((machine.id, day, shift_id), 1) == 0:
                    continue
                if availability.get((machine.id, day), 1) == 0:
                    continue
                if (machine.id, day, shift_id) in blackout:
                    continue
                r = rate.get((machine.id, block_id), 0.0)
                if r <= 0.0:
                    continue
                if r > best_rate:
                    best_rate = r
                    best_slot = (machine.id, day, shift_id)
        return best_slot

    # Respect locked assignments up front.
    for shift in shifts:
        day, shift_id = shift.day, shift.shift_id
        for machine in sc.machines:
            lock_block = locked.get((machine.id, day))
            if lock_block is None:
                continue
            assign(machine.id, day, shift_id, lock_block)

    # Coverage pass: ensure every block is started if feasible.
    blocks_by_window = sorted(
        sc.blocks,
        key=lambda blk: (*sc.window_for(blk.id), blk.id),
    )
    while True:
        progress = False
        for block in blocks_by_window:
            block_id = block.id
            if remaining[block_id] <= 1e-9:
                continue
            slot = best_slot_for(block_id)
            if slot is None:
                continue
            assign(*slot, block_id)
            progress = True
        if not progress:
            break

    # Fill remaining slots greedily with best-rate assignments.
    for shift in shifts:
        day, shift_id = shift.day, shift.shift_id
        for machine in sc.machines:
            if plan[machine.id][(day, shift_id)] is not None:
                continue
            if shift_availability.get((machine.id, day, shift_id), 1) == 0:
                continue
            if availability.get((machine.id, day), 1) == 0:
                continue
            if (machine.id, day, shift_id) in blackout:
                continue
            candidates: list[tuple[float, str]] = []
            for block in sc.blocks:
                if remaining[block.id] <= 1e-9:
                    continue
                earliest, latest = windows[block.id]
                if day < earliest or day > latest:
                    continue
                allowed = allowed_roles.get(block.id)
                role = machine_roles.get(machine.id)
                if allowed is not None and role is not None and role not in allowed:
                    continue
                r = rate.get((machine.id, block.id), 0.0)
                if r > 0:
                    candidates.append((r, block.id))
            if candidates:
                candidates.sort(reverse=True)
                _, best_block = candidates[0]
                assign(machine.id, day, shift_id, best_block)
    return Schedule(plan=plan)


def _evaluate(pb: Problem, sched: Schedule, ctx: OperationalProblem) -> float:
    """Score a schedule using production, mobilisation, transition, and slack penalties."""
    sc = pb.scenario
    bundle = ctx.bundle
    remaining = dict(bundle.work_required)
    rate = bundle.production_rates
    windows = bundle.windows
    landing_of = bundle.landing_for_block
    landing_cap = bundle.landing_capacity
    mobil_params: dict[str, MachineMobilisation] = dict(ctx.mobilisation_params)
    distance_lookup = ctx.distance_lookup

    allowed_roles = ctx.allowed_roles
    prereq_roles = ctx.prereq_roles
    machine_roles = bundle.machine_roles
    blackout = ctx.blackout_shifts
    locked = ctx.locked_assignments
    shift_availability = bundle.availability_shift
    availability = bundle.availability_day

    weights = bundle.objective_weights
    prod_weight = weights.production
    mobil_weight = weights.mobilisation
    transition_weight = weights.transitions
    landing_slack_weight = weights.landing_slack

    production_total = 0.0
    initial_work_required = dict(bundle.work_required)
    mobilisation_total = 0.0
    transition_count = 0.0
    landing_slack_total = 0.0
    penalty = 0.0

    previous_block: dict[str, str | None] = {machine.id: None for machine in sc.machines}
    unfinished_block: dict[str, str | None] = {machine.id: None for machine in sc.machines}
    role_cumulative: defaultdict[tuple[str, str], int] = defaultdict(int)
    shifts = sorted(pb.shifts, key=lambda s: (s.day, s.shift_id))

    def select_alternate_block(machine_id: str, day: int, shift_id: str) -> str | None:
        role = machine_roles.get(machine_id)
        best_block: str | None = None
        best_rate = 0.0
        for block in sc.blocks:
            remaining_work = remaining[block.id]
            if remaining_work <= BLOCK_COMPLETION_EPS:
                continue
            earliest, latest = windows[block.id]
            if day < earliest or day > latest:
                continue
            allowed = allowed_roles.get(block.id)
            if allowed is not None and role is not None and role not in allowed:
                continue
            r = rate.get((machine_id, block.id), 0.0)
            if r <= 0.0:
                continue
            if r > best_rate:
                best_rate = r
                best_block = block.id
        return best_block

    for shift in shifts:
        day = shift.day
        shift_id = shift.shift_id
        used = {landing.id: 0 for landing in sc.landings}
        shift_role_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        for machine in sc.machines:
            planned_block = sched.plan[machine.id][(day, shift_id)]
            block_id = planned_block
            lock_key = (machine.id, day)

            shift_available = shift_availability.get((machine.id, day, shift_id), 1)
            day_available = availability.get((machine.id, day), 1)
            if shift_available == 0 or day_available == 0:
                penalty += 1000.0
                previous_block[machine.id] = None
                continue
            if (machine.id, day, shift_id) in blackout:
                penalty += 1000.0
                previous_block[machine.id] = None
                continue

            locked_block = locked.get(lock_key)
            if locked_block is not None:
                if block_id is not None and block_id != locked_block:
                    penalty += 1000.0
                block_id = locked_block

            active_block = unfinished_block[machine.id]
            if active_block and remaining[active_block] <= BLOCK_COMPLETION_EPS:
                active_block = None
                unfinished_block[machine.id] = None

            if active_block is not None:
                if block_id is None or block_id != active_block:
                    block_id = active_block

            sched.plan[machine.id][(day, shift_id)] = block_id
            if block_id is None:
                continue

            allowed = allowed_roles.get(block_id)
            role: str | None = machine_roles.get(machine.id)
            if allowed is not None and role is not None and role not in allowed:
                penalty += 1000.0
                previous_block[machine.id] = None
                continue
            if role is None:
                prereq_set = None
            else:
                prereq_set = prereq_roles.get((block_id, role))
            if prereq_set:
                assert role is not None
                role_key = (block_id, role)
                available = min(role_cumulative[(block_id, prereq)] for prereq in prereq_set)
                required = role_cumulative[role_key] + shift_role_counts[role_key] + 1
                if required > available:
                    penalty += 1000.0
                    previous_block[machine.id] = block_id
                    continue
            earliest, latest = windows[block_id]
            if day < earliest or day > latest:
                block_id = select_alternate_block(machine.id, day, shift_id)
                if block_id is None:
                    continue
                sched.plan[machine.id][(day, shift_id)] = block_id
            if remaining[block_id] <= 1e-9:
                alternate = select_alternate_block(machine.id, day, shift_id)
                if alternate is None:
                    continue
                block_id = alternate
                sched.plan[machine.id][(day, shift_id)] = block_id
            landing_id = landing_of[block_id]
            capacity = landing_cap[landing_id]
            next_usage = used[landing_id] + 1
            excess = max(0, next_usage - capacity)
            if excess > 0:
                if landing_slack_weight == 0.0:
                    penalty += 1000.0
                    continue
                landing_slack_total += excess
            used[landing_id] = next_usage
            r = rate.get((machine.id, block_id), 0.0)
            prod = min(r, remaining[block_id])
            remaining[block_id] -= prod
            production_total += prod
            if remaining[block_id] > BLOCK_COMPLETION_EPS:
                unfinished_block[machine.id] = block_id
            else:
                unfinished_block[machine.id] = None
            params = mobil_params.get(machine.id)
            prev_blk = previous_block[machine.id]
            if params is not None and prev_blk is not None and block_id is not None:
                if block_id != prev_blk:
                    distance = distance_lookup.get((prev_blk, block_id), 0.0)
                    cost = params.setup_cost
                    if distance <= params.walk_threshold_m:
                        cost += params.walk_cost_per_meter * distance
                    else:
                        cost += params.move_cost_flat
                    mobilisation_total += cost
                    transition_count += 1.0
                else:
                    # no mobilisation cost but still record no transition change
                    pass
            else:
                if prev_blk is not None and block_id != prev_blk:
                    transition_count += 1.0
            previous_block[machine.id] = block_id
            if role is not None:
                shift_role_counts[(block_id, role)] += 1
        for key, count in shift_role_counts.items():
            role_cumulative[key] += count
    completion_bonus = sum(
        initial_work_required[block_id]
        for block_id, remaining_work in remaining.items()
        if remaining_work <= BLOCK_COMPLETION_EPS
    )
    leftover_total = sum(
        remaining_work
        for remaining_work in remaining.values()
        if remaining_work > BLOCK_COMPLETION_EPS
    )
    partial_weight = prod_weight * PARTIAL_PRODUCTION_FRACTION
    score = (prod_weight * (completion_bonus - LEFTOVER_PENALTY_FACTOR * leftover_total)) + (
        partial_weight * production_total
    )
    score -= mobil_weight * mobilisation_total
    score -= transition_weight * transition_count
    score -= landing_slack_weight * landing_slack_total
    score -= penalty
    return score


def _neighbors(
    pb: Problem,
    sched: Schedule,
    registry: OperatorRegistry,
    rng: _random.Random,
    operator_stats: dict[str, dict[str, float]],
    ctx: OperationalProblem,
    *,
    batch_size: int | None = None,
) -> list[Schedule]:
    """Generate neighbour schedules via enabled operators with feasibility sanitization."""
    sc = pb.scenario
    if not sc.machines or not pb.shifts:
        return []
    block_windows = ctx.bundle.windows
    landing_cap = ctx.bundle.landing_capacity
    landing_of = ctx.bundle.landing_for_block
    distance_lookup = ctx.distance_lookup

    schedule_cls = sched.__class__
    sanitizer = ctx.build_sanitizer(schedule_cls)

    context = OperatorContext(
        problem=pb,
        schedule=sched,
        sanitizer=sanitizer,
        rng=rng,
        distance_lookup=distance_lookup,
        block_windows=block_windows,
        landing_capacity=landing_cap,
        landing_of=landing_of,
    )

    enabled_ops = list(registry.enabled())
    if not enabled_ops:
        return []

    ordered_ops = []
    if len(enabled_ops) <= 1:
        ordered_ops = list(enabled_ops)
    else:
        weight_values = [op.weight for op in enabled_ops]
        if all(abs(w - weight_values[0]) < 1e-9 for w in weight_values):
            ordered_ops = list(enabled_ops)
        else:
            candidates = enabled_ops.copy()
            weights = [op.weight for op in candidates]
            while candidates:
                total = sum(weights)
                if total <= 0:
                    ordered_ops.extend(candidates)
                    break
                pick = rng.random() * total
                cumulative = 0.0
                for idx, (op, weight) in enumerate(zip(candidates, weights)):
                    cumulative += weight
                    if pick <= cumulative:
                        ordered_ops.append(op)
                        candidates.pop(idx)
                        weights.pop(idx)
                        break

    limit = batch_size if batch_size is not None and batch_size > 0 else None
    neighbours: list[Schedule] = []
    for operator in ordered_ops:
        stats = operator_stats.setdefault(
            operator.name, {"proposals": 0.0, "accepted": 0.0, "weight": operator.weight}
        )
        stats["weight"] = operator.weight
        stats["proposals"] += 1.0

        candidate = operator.apply(context)
        if candidate is not None:
            neighbours.append(candidate)
            stats["accepted"] += 1.0
            if limit is not None and len(neighbours) >= limit:
                break
        else:
            stats.setdefault("skipped", 0.0)
            stats["skipped"] += 1.0
    return neighbours


def _evaluate_candidates(
    pb: Problem,
    candidates: list[Schedule],
    ctx: OperationalProblem,
    max_workers: int | None = None,
) -> list[tuple[Schedule, float]]:
    """Evaluate candidate schedules, optionally in parallel, returning (schedule, score)."""
    if not candidates:
        return []
    if max_workers is None or max_workers <= 1 or len(candidates) == 1:
        return [(candidate, _evaluate(pb, candidate, ctx)) for candidate in candidates]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        def _score(schedule: Schedule) -> float:
            return _evaluate(pb, schedule, ctx)

        scores = list(executor.map(_score, candidates))
    return list(zip(candidates, scores))


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

    if not 0 < cooling_rate < 1:
        raise ValueError("cooling_rate must be between 0 and 1 (exclusive).")
    restart_interval_value = (
        restart_interval
        if restart_interval and restart_interval > 0
        else max(1000, iters // 5 or 200)
    )

    config_snapshot: dict[str, Any] = {
        "iters": iters,
        "batch_size": batch_size,
        "max_workers": max_workers,
        "cooling_rate": cooling_rate,
        "restart_interval": restart_interval_value,
        "operators": registry.weights(),
    }
    context_payload = dict(telemetry_context or {})
    step_interval = context_payload.pop("step_interval", 100)
    tuner_meta = context_payload.pop("tuner_meta", None)
    scenario_name = getattr(pb.scenario, "name", None)
    scenario_path = context_payload.pop("scenario_path", None)

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

    with telemetry_logger if telemetry_logger else nullcontext() as run_logger:
        current = _init_greedy(pb, ctx)
        current_score = _evaluate(pb, current, ctx)
        best = current
        best_score = current_score

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
            candidates = _neighbors(
                pb,
                current,
                registry,
                rng,
                operator_stats,
                ctx,
                batch_size=batch_size,
            )
            evaluations = _evaluate_candidates(
                pb,
                candidates,
                ctx,
                max_workers=max_workers if batch_size and batch_size > 1 else None,
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
                    break
            if current_score > best_score:
                best, best_score = current, current_score
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

            if stalled_steps >= restart_interval_value:
                current = _init_greedy(pb, ctx)
                current_score = _evaluate(pb, current, ctx)
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
                        metadata=watch_meta,
                    )
                )

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
                    metadata=watch_meta,
                )
            )
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
        }
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
                    "acceptance_rate": meta["acceptance_rate"],
                    **numeric_kpis,
                },
                extra={
                    "iterations": iters,
                    "restarts": restarts,
                    "proposals": proposals,
                    "accepted_moves": accepted_moves,
                    "temperature0": float(temperature0),
                    "operators": registry.weights(),
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
