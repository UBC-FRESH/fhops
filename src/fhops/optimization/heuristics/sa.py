"""Simulated annealing heuristic for FHOPS."""

from __future__ import annotations

import math
import random as _random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics.registry import OperatorContext, OperatorRegistry
from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import MachineMobilisation, build_distance_lookup
from fhops.telemetry import RunTelemetryLogger


def _role_metadata(scenario):
    systems = scenario.harvest_systems or {}
    allowed: dict[str, set[str] | None] = {}
    prereqs: dict[tuple[str, str], set[str]] = {}
    for block in scenario.blocks:
        system = systems.get(block.harvest_system_id) if block.harvest_system_id else None
        if system:
            job_role = {job.name: job.machine_role for job in system.jobs}
            allowed_roles = {job.machine_role for job in system.jobs}
            allowed[block.id] = allowed_roles
            for job in system.jobs:
                prereq_roles = {job_role[name] for name in job.prerequisites if name in job_role}
                prereqs[(block.id, job.machine_role)] = prereq_roles
        else:
            allowed[block.id] = None

    machine_roles = {machine.id: getattr(machine, "role", None) for machine in scenario.machines}
    machines_by_role: dict[str, list[str]] = {}
    for machine_id, role in machine_roles.items():
        if role is None:
            continue
        machines_by_role.setdefault(role, []).append(machine_id)

    return allowed, prereqs, machine_roles, machines_by_role


def _blackout_map(scenario) -> set[tuple[str, int, str]]:
    blackout: set[tuple[str, int, str]] = set()
    timeline = getattr(scenario, "timeline", None)
    if timeline and timeline.blackouts:
        for blackout_window in timeline.blackouts:
            for day in range(blackout_window.start_day, blackout_window.end_day + 1):
                for machine in scenario.machines:
                    if scenario.shift_calendar:
                        for entry in scenario.shift_calendar:
                            if entry.machine_id == machine.id and entry.day == day:
                                blackout.add((machine.id, day, entry.shift_id))
                    elif timeline.shifts:
                        for shift_def in timeline.shifts:
                            blackout.add((machine.id, day, shift_def.name))
                    else:
                        blackout.add((machine.id, day, "S1"))
    return blackout


def _locked_map(scenario) -> dict[tuple[str, int], str]:
    locks = getattr(scenario, "locked_assignments", None)
    if not locks:
        return {}
    return {(lock.machine_id, lock.day): lock.block_id for lock in locks}


__all__ = ["Schedule", "solve_sa"]


@dataclass(slots=True)
class Schedule:
    """Machine assignment plan keyed by machine/(day, shift_id)."""

    plan: dict[str, dict[tuple[int, str], str | None]]


def _init_greedy(pb: Problem) -> Schedule:
    sc = pb.scenario
    remaining = {block.id: block.work_required for block in sc.blocks}
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    shift_availability = (
        {(c.machine_id, c.day, c.shift_id): int(c.available) for c in sc.shift_calendar}
        if sc.shift_calendar
        else {}
    )
    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    windows = {block_id: sc.window_for(block_id) for block_id in sc.block_ids()}
    allowed_roles, prereq_roles, machine_roles, _ = _role_metadata(sc)
    blackout = _blackout_map(sc)
    locked = _locked_map(sc)
    shift_availability = (
        {(c.machine_id, c.day, c.shift_id): int(c.available) for c in sc.shift_calendar}
        if sc.shift_calendar
        else {}
    )
    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}

    shifts = [(shift.day, shift.shift_id) for shift in pb.shifts]
    plan: dict[str, dict[tuple[int, str], str | None]] = {
        machine.id: {(day, shift_id): None for day, shift_id in shifts} for machine in sc.machines
    }

    for day, shift_id in shifts:
        for machine in sc.machines:
            if shift_availability:
                if shift_availability.get((machine.id, day, shift_id), 1) == 0:
                    continue
            if availability.get((machine.id, day), 1) == 0:
                continue
            lock_key = (machine.id, day)
            if lock_key in locked:
                plan[machine.id][(day, shift_id)] = locked[lock_key]
                continue
            if (machine.id, day, shift_id) in blackout:
                continue
            candidates: list[tuple[float, str]] = []
            for block in sc.blocks:
                earliest, latest = windows[block.id]
                if day < earliest or day > latest or remaining[block.id] <= 1e-9:
                    continue
                allowed = allowed_roles.get(block.id)
                role = machine_roles.get(machine.id)
                if allowed is not None and role not in allowed:
                    continue
                r = rate.get((machine.id, block.id), 0.0)
                if r > 0:
                    candidates.append((r, block.id))
            if candidates:
                candidates.sort(reverse=True)
                _, best_block = candidates[0]
                plan[machine.id][(day, shift_id)] = best_block
                remaining[best_block] = max(
                    0.0, remaining[best_block] - rate.get((machine.id, best_block), 0.0)
                )
    return Schedule(plan=plan)


def _evaluate(pb: Problem, sched: Schedule) -> float:
    sc = pb.scenario
    remaining = {block.id: block.work_required for block in sc.blocks}
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    windows = {block_id: sc.window_for(block_id) for block_id in sc.block_ids()}
    landing_of = {block.id: block.landing_id for block in sc.blocks}
    landing_cap = {landing.id: landing.daily_capacity for landing in sc.landings}
    mobilisation = sc.mobilisation
    mobil_params: dict[str, MachineMobilisation] = {}
    distance_lookup = build_distance_lookup(mobilisation)
    if mobilisation is not None:
        mobil_params = {param.machine_id: param for param in mobilisation.machine_params}

    allowed_roles, prereq_roles, machine_roles, _ = _role_metadata(sc)
    blackout = _blackout_map(sc)
    locked = _locked_map(sc)
    shift_availability = (
        {(c.machine_id, c.day, c.shift_id): int(c.available) for c in sc.shift_calendar}
        if sc.shift_calendar
        else {}
    )
    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}

    weights = getattr(sc, "objective_weights", None)
    prod_weight = weights.production if weights else 1.0
    mobil_weight = weights.mobilisation if weights else 1.0
    transition_weight = weights.transitions if weights else 0.0
    landing_slack_weight = weights.landing_slack if weights else 0.0

    production_total = 0.0
    mobilisation_total = 0.0
    transition_count = 0.0
    landing_slack_total = 0.0
    penalty = 0.0

    previous_block: dict[str, str | None] = {machine.id: None for machine in sc.machines}
    role_cumulative: defaultdict[tuple[str, str], int] = defaultdict(int)
    shifts = sorted(pb.shifts, key=lambda s: (s.day, s.shift_id))
    for shift in shifts:
        day = shift.day
        shift_id = shift.shift_id
        used = {landing.id: 0 for landing in sc.landings}
        shift_role_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        for machine in sc.machines:
            block_id = sched.plan[machine.id][(day, shift_id)]
            if block_id is None:
                if (machine.id, day) in locked:
                    penalty += 1000.0
                continue
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
            if (machine.id, day) in locked and locked[(machine.id, day)] != block_id:
                penalty += 1000.0
                previous_block[machine.id] = None
                continue
            allowed = allowed_roles.get(block_id)
            role: str | None = machine_roles.get(machine.id)
            if allowed is not None and (role is None or role not in allowed):
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
                continue
            if remaining[block_id] <= 1e-9:
                continue
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
    score = prod_weight * production_total
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
    *,
    batch_size: int | None = None,
) -> list[Schedule]:
    sc = pb.scenario
    if not sc.machines or not pb.shifts:
        return []
    allowed_roles, _, machine_roles, _ = _role_metadata(sc)
    blackout = _blackout_map(sc)
    locked = _locked_map(sc)
    shift_availability = (
        {(c.machine_id, c.day, c.shift_id): int(c.available) for c in sc.shift_calendar}
        if sc.shift_calendar
        else {}
    )
    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    landing_of = {block.id: block.landing_id for block in sc.blocks}
    landing_cap = {landing.id: landing.daily_capacity for landing in sc.landings}
    block_windows = {block.id: sc.window_for(block.id) for block in sc.blocks}
    distance_lookup = build_distance_lookup(sc.mobilisation)

    schedule_cls = sched.__class__

    def sanitizer(candidate: Schedule) -> Schedule:
        plan: dict[str, dict[tuple[int, str], str | None]] = {}
        landing_usage: dict[tuple[int, str, str], int] = {}
        for mach, assignments in candidate.plan.items():
            role = machine_roles.get(mach)
            plan[mach] = {}
            for shift_key_iter, blk in assignments.items():
                day_key = shift_key_iter[0]
                allowed = allowed_roles.get(blk) if blk is not None else None
                if (mach, day_key) in locked:
                    plan[mach][shift_key_iter] = locked[(mach, day_key)]
                    continue
                shift_available = shift_availability.get((mach, day_key, shift_key_iter[1]), 1)
                day_available = availability.get((mach, day_key), 1)
                if blk is not None and (
                    shift_available == 0
                    or day_available == 0
                    or (mach, day_key, shift_key_iter[1]) in blackout
                    or (allowed is not None and role not in allowed)
                ):
                    plan[mach][shift_key_iter] = None
                else:
                    landing_id = landing_of.get(blk) if blk is not None else None
                    if landing_id is not None:
                        key = (day_key, shift_key_iter[1], landing_id)
                        cap = landing_cap.get(landing_id, 0)
                        current = landing_usage.get(key, 0)
                        if cap > 0 and current >= cap:
                            plan[mach][shift_key_iter] = None
                            continue
                        landing_usage[key] = current + 1
                    plan[mach][shift_key_iter] = blk
        return schedule_cls(plan=plan)

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
    max_workers: int | None = None,
) -> list[tuple[Schedule, float]]:
    if not candidates:
        return []
    if max_workers is None or max_workers <= 1 or len(candidates) == 1:
        return [(candidate, _evaluate(pb, candidate)) for candidate in candidates]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        scores = list(executor.map(lambda sched: _evaluate(pb, sched), candidates))
    return list(zip(candidates, scores))


def solve_sa(
    pb: Problem,
    iters: int = 2000,
    seed: int = 42,
    operators: list[str] | None = None,
    operator_weights: dict[str, float] | None = None,
    batch_size: int | None = None,
    max_workers: int | None = None,
    telemetry_log: str | Path | None = None,
    telemetry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Solve the scheduling problem with simulated annealing.

    Parameters
    ----------
    pb:
        Parsed :class:`~fhops.scenario.contract.Problem` describing the scenario.
    iters:
        Number of annealing iterations. Higher values increase runtime and solution quality.
    seed:
        RNG seed used for deterministic runs.
    operators:
        Optional list of operator names to enable (default: all registered operators).
    operator_weights:
        Optional weight overrides for operators (values ``<= 0`` disable an operator).
    batch_size:
        When set, sample up to ``batch_size`` neighbour candidates per iteration.
        ``None`` or ``<= 1`` keeps the sequential single-candidate behaviour.
    max_workers:
        Maximum worker threads for evaluating batched neighbours. ``None``/``<=1`` keeps sequential scoring.

    Returns
    -------
    dict
        Dictionary containing the best objective, assignments DataFrame, and telemetry metadata.
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

    config_snapshot: dict[str, Any] = {
        "iters": iters,
        "batch_size": batch_size,
        "max_workers": max_workers,
        "operators": registry.weights(),
    }
    context_payload = dict(telemetry_context or {})
    step_interval = context_payload.pop("step_interval", 100)
    tuner_meta = context_payload.pop("tuner_meta", None)
    scenario_name = getattr(pb.scenario, "name", None)
    scenario_path = context_payload.pop("scenario_path", None)

    telemetry_logger: RunTelemetryLogger | None = None
    if telemetry_log:
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
            log_path=telemetry_log,
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

    with telemetry_logger if telemetry_logger else nullcontext() as run_logger:
        current = _init_greedy(pb)
        current_score = _evaluate(pb, current)
        best = current
        best_score = current_score

        temperature0 = max(1.0, best_score / 10.0)
        temperature = temperature0
        initial_score = current_score
        proposals = 0
        accepted_moves = 0
        restarts = 0
        operator_stats: dict[str, dict[str, float]] = {}
        for step in range(1, iters + 1):
            accepted = False
            candidates = _neighbors(
                pb,
                current,
                registry,
                rng,
                operator_stats,
                batch_size=batch_size,
            )
            evaluations = _evaluate_candidates(
                pb,
                candidates,
                max_workers=max_workers if batch_size and batch_size > 1 else None,
            )
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
            temperature = temperature0 * (0.995**step)
            if run_logger and telemetry_logger and telemetry_logger.step_interval:
                if step == 1 or step == iters or (step % telemetry_logger.step_interval == 0):
                    acceptance_rate = (accepted_moves / proposals) if proposals else 0.0
                    run_logger.log_step(
                        step=step,
                        objective=float(current_score),
                        best_objective=float(best_score),
                        temperature=float(temperature),
                        acceptance_rate=acceptance_rate,
                        proposals=proposals,
                        accepted_moves=accepted_moves,
                    )
            if not accepted and step % 100 == 0:
                current = _init_greedy(pb)
                current_score = _evaluate(pb, current)
                restarts += 1

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
            "proposals": proposals,
            "accepted_moves": accepted_moves,
            "acceptance_rate": (accepted_moves / proposals) if proposals else 0.0,
            "restarts": restarts,
            "iterations": iters,
            "temperature0": float(temperature0),
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
