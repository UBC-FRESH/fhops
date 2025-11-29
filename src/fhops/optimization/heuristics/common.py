"""Shared schedule helpers for heuristics (greedy seed, evaluation, neighbours)."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from fhops.evaluation.sequencing import SequencingTracker, build_role_priority
from fhops.optimization.heuristics.registry import OperatorContext, OperatorRegistry
from fhops.optimization.operational_problem import OperationalProblem
from fhops.scenario.contract import Problem

BLOCK_COMPLETION_EPS = 1e-6
PARTIAL_PRODUCTION_FRACTION = 0.1
LEFTOVER_PENALTY_FACTOR = 5.0


@dataclass(slots=True)
class Schedule:
    """Machine assignment plan keyed by machine/(day, shift_id)."""

    plan: dict[str, dict[tuple[int, str], str | None]]


def _repair_schedule_cover_blocks(
    pb: Problem,
    sched: Schedule,
    ctx: OperationalProblem,
    *,
    fill_voids: bool = True,
) -> None:
    """Fill empty/invalid shifts with high-demand blocks per role."""

    sc = pb.scenario
    bundle = ctx.bundle
    rate = bundle.production_rates
    windows = bundle.windows
    machine_roles = bundle.machine_roles
    shift_availability = bundle.availability_shift
    availability = bundle.availability_day
    blackout = ctx.blackout_shifts
    locked = ctx.locked_assignments
    role_remaining = dict(ctx.role_work_required)
    block_remaining = dict(bundle.work_required)
    block_system = bundle.block_system
    explicit_blocks = ctx.blocks_with_explicit_system
    prereq_roles = ctx.prereq_roles
    role_headstarts = ctx.role_headstarts
    role_priority = build_role_priority(ctx)

    shifts = sorted(pb.shifts, key=lambda s: (s.day, s.shift_id))
    shift_keys = [(shift.day, shift.shift_id) for shift in shifts]

    plan = sched.plan
    for machine in sc.machines:
        machine_plan = plan.setdefault(machine.id, {})
        for key in shift_keys:
            machine_plan.setdefault(key, None)

    ordered_machines = sorted(
        sc.machines,
        key=lambda m: (role_priority.get(machine_roles.get(m.id) or "", 999), m.id),
    )

    role_inventory_estimate: defaultdict[tuple[str, str], float] = defaultdict(float)
    role_inventory_today: defaultdict[tuple[str, str], float] = defaultdict(float)
    current_day: int | None = None
    role_counts_total: defaultdict[tuple[str, str], int] = defaultdict(int)
    role_counts_day: defaultdict[tuple[str, str], int] = defaultdict(int)

    def is_terminal(block_id: str, role: str | None) -> bool:
        if block_id not in explicit_blocks:
            return True
        if role is None:
            return True
        system_id = block_system.get(block_id)
        if system_id is None:
            return True
        terminal = ctx.terminal_roles.get(system_id)
        if not terminal:
            return True
        return role in terminal

    def compute_production(machine_id: str, block_id: str, role: str | None) -> float:
        base_rate = rate.get((machine_id, block_id), 0.0)
        if base_rate <= 0.0:
            return 0.0
        if block_id in explicit_blocks and role is not None and (block_id, role) in role_remaining:
            return min(base_rate, role_remaining[(block_id, role)])
        return min(base_rate, block_remaining.get(block_id, base_rate))

    def has_inventory(block_id: str, role: str | None, production: float) -> bool:
        if block_id not in explicit_blocks or role is None:
            return True
        prereqs = prereq_roles.get((block_id, role))
        if not prereqs:
            return True
        available_volume = min(
            role_inventory_estimate[(block_id, upstream)] for upstream in prereqs
        )
        loader_requirement = 0.0
        if (block_id, role) in ctx.loader_roles:
            loader_requirement = min(
                ctx.loader_batch_volume.get(block_id, 0.0),
                block_remaining.get(block_id, 0.0),
            )
        required_volume = max(production, loader_requirement)
        return available_volume + 1e-9 >= required_volume

    def meets_headstart(block_id: str, role: str | None) -> bool:
        if block_id not in explicit_blocks or role is None:
            return True
        buffer = role_headstarts.get((block_id, role), 0.0)
        if buffer <= 0.0:
            return True
        prereqs = prereq_roles.get((block_id, role))
        if not prereqs:
            return True
        downstream_total = role_counts_total[(block_id, role)]
        for upstream in prereqs:
            upstream_total = role_counts_total[(block_id, upstream)]
            if (upstream_total - downstream_total) + 1e-9 < buffer:
                return False
        return True

    def advance_day(day: int) -> None:
        nonlocal current_day
        if current_day is None:
            current_day = day
            return
        if day == current_day:
            return
        for key, volume in role_inventory_today.items():
            role_inventory_estimate[key] += volume
        role_inventory_today.clear()
        for key, count in role_counts_day.items():
            role_counts_total[key] += count
        role_counts_day.clear()
        current_day = day

    def has_demand(block_id: str, role: str | None) -> bool:
        if block_id in explicit_blocks and role is not None and (block_id, role) in role_remaining:
            return role_remaining.get((block_id, role), 0.0) > BLOCK_COMPLETION_EPS
        return block_remaining.get(block_id, 0.0) > BLOCK_COMPLETION_EPS

    def record_assignment(machine_id: str, block_id: str) -> None:
        role = machine_roles.get(machine_id)
        production = compute_production(machine_id, block_id, role)
        if production <= BLOCK_COMPLETION_EPS:
            return
        if block_id in explicit_blocks and role is not None:
            prereqs = prereq_roles.get((block_id, role))
            if prereqs:
                for upstream in prereqs:
                    key = (block_id, upstream)
                    role_inventory_estimate[key] = max(
                        0.0, role_inventory_estimate.get(key, 0.0) - production
                    )
            role_inventory_today[(block_id, role)] += production
            if (block_id, role) in role_remaining:
                role_remaining[(block_id, role)] = max(
                    0.0, role_remaining[(block_id, role)] - production
                )
            if is_terminal(block_id, role):
                block_remaining[block_id] = max(
                    0.0, block_remaining.get(block_id, 0.0) - production
                )
            role_counts_day[(block_id, role)] += 1
        else:
            block_remaining[block_id] = max(0.0, block_remaining.get(block_id, 0.0) - production)

    def slot_is_valid(
        machine_id: str,
        day: int,
        block_id: str | None,
        role: str | None,
        *,
        enforce_prereq: bool = True,
    ) -> bool:
        if block_id is None:
            return False
        earliest, latest = windows[block_id]
        if day < earliest or day > latest:
            return False
        rate_value = rate.get((machine_id, block_id), 0.0)
        if rate_value <= 0.0:
            return False
        allowed = ctx.allowed_roles.get(block_id)
        if allowed is not None and role is not None and role not in allowed:
            return False
        if not has_demand(block_id, role):
            return False
        production = compute_production(machine_id, block_id, role)
        if production <= BLOCK_COMPLETION_EPS:
            return False
        if enforce_prereq and (
            not has_inventory(block_id, role, production) or not meets_headstart(block_id, role)
        ):
            return False
        return True

    def pending_blocks_for(role: str | None) -> list[str]:
        demand: list[tuple[str, float]] = []
        if role is not None:
            for (block_id, role_name), remaining in role_remaining.items():
                if role_name == role and remaining > BLOCK_COMPLETION_EPS:
                    demand.append((block_id, remaining))
        for block_id, remaining in block_remaining.items():
            if remaining <= BLOCK_COMPLETION_EPS:
                continue
            if (
                role is not None
                and (block_id, role) in role_remaining
                and block_id in explicit_blocks
            ):
                continue
            demand.append((block_id, remaining))
        demand.sort(key=lambda item: item[1], reverse=True)
        return [block_id for block_id, _ in demand]

    def select_block(machine_id: str, day: int, shift_id: str, role: str | None) -> str | None:
        best_block: str | None = None
        best_rate = 0.0
        for block_id in pending_blocks_for(role):
            if not slot_is_valid(machine_id, day, block_id, role):
                continue
            candidate_rate = rate.get((machine_id, block_id), 0.0)
            if candidate_rate <= best_rate:
                continue
            best_block = block_id
            best_rate = candidate_rate
        return best_block

    for day, shift_id in shift_keys:
        advance_day(day)
        for machine in ordered_machines:
            role = machine_roles.get(machine.id)
            slot_key = (day, shift_id)
            machine_plan = plan[machine.id]
            block_id = machine_plan.get(slot_key)
            lock_block = locked.get((machine.id, day))
            locked_slot = lock_block is not None
            if locked_slot:
                block_id = lock_block
                machine_plan[slot_key] = block_id
            if shift_availability.get((machine.id, day, shift_id), 1) == 0:
                machine_plan[slot_key] = None
                continue
            if availability.get((machine.id, day), 1) == 0:
                machine_plan[slot_key] = None
                continue
            if (machine.id, day, shift_id) in blackout:
                machine_plan[slot_key] = None
                continue
            if block_id is not None:
                if not slot_is_valid(
                    machine.id,
                    day,
                    block_id,
                    role,
                    enforce_prereq=not locked_slot,
                ):
                    block_id = None
                    machine_plan[slot_key] = None
            if block_id is None and fill_voids:
                candidate = select_block(machine.id, day, shift_id, role)
                if candidate is None:
                    machine_plan[slot_key] = None
                    continue
                machine_plan[slot_key] = candidate
                block_id = candidate
            if block_id is not None:
                record_assignment(machine.id, block_id)

    if not fill_voids:
        return


def init_greedy_schedule(pb: Problem, ctx: OperationalProblem) -> Schedule:
    """Construct an initial Schedule by greedily filling shifts with best-rate blocks."""

    sc = pb.scenario
    bundle = ctx.bundle
    remaining = dict(bundle.work_required)
    role_remaining = dict(ctx.role_work_required)
    rate = bundle.production_rates
    shift_availability = bundle.availability_shift
    availability = bundle.availability_day
    windows = bundle.windows
    allowed_roles = ctx.allowed_roles
    machine_roles = bundle.machine_roles
    blackout = ctx.blackout_shifts
    locked = ctx.locked_assignments
    block_system = bundle.block_system
    explicit_blocks = ctx.blocks_with_explicit_system

    def _is_terminal(block_id: str, role: str | None) -> bool:
        if block_id not in explicit_blocks:
            return True
        if role is None:
            return True
        system_id = block_system.get(block_id)
        if system_id is None:
            return True
        terminal = ctx.terminal_roles.get(system_id)
        if not terminal:
            return True
        return role in terminal

    def _role_demand(block_id: str, role: str | None) -> float:
        if block_id in explicit_blocks and role is not None:
            return role_remaining.get((block_id, role), 0.0)
        return remaining.get(block_id, 0.0)

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
        role = machine_roles.get(machine_id)
        base_rate = rate.get((machine_id, block_id), 0.0)
        if base_rate <= 0.0:
            return
        if block_id in explicit_blocks and role is not None and (block_id, role) in role_remaining:
            production = min(base_rate, role_remaining[(block_id, role)])
            role_remaining[(block_id, role)] = max(
                0.0, role_remaining[(block_id, role)] - production
            )
            if _is_terminal(block_id, role):
                remaining[block_id] = max(0.0, remaining[block_id] - production)
        else:
            production = min(base_rate, remaining[block_id])
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
            if _role_demand(block_id, role) <= BLOCK_COMPLETION_EPS:
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
            if _role_demand(block_id, None) <= BLOCK_COMPLETION_EPS:
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
                role = machine_roles.get(machine.id)
                if _role_demand(block.id, role) <= BLOCK_COMPLETION_EPS:
                    continue
                earliest, latest = windows[block.id]
                if day < earliest or day > latest:
                    continue
                allowed = allowed_roles.get(block.id)
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


def evaluate_schedule(
    pb: Problem,
    sched: Schedule,
    ctx: OperationalProblem,
    debug: dict[str, Any] | None = None,
) -> float:
    """Score a schedule using production, mobilisation, transition, and slack penalties."""

    _repair_schedule_cover_blocks(pb, sched, ctx)

    sc = pb.scenario
    bundle = ctx.bundle
    rate = bundle.production_rates
    windows = bundle.windows
    landing_of = bundle.landing_for_block
    landing_cap = bundle.landing_capacity
    mobil_params = dict(ctx.mobilisation_params)
    distance_lookup = ctx.distance_lookup

    allowed_roles = ctx.allowed_roles
    blackout = ctx.blackout_shifts
    locked = ctx.locked_assignments
    shift_availability = bundle.availability_shift
    availability = bundle.availability_day

    weights = bundle.objective_weights

    production_total = 0.0
    initial_work_required = dict(bundle.work_required)
    mobilisation_total = 0.0
    transition_count = 0.0
    landing_slack_total = 0.0
    penalty = 0.0

    previous_block: dict[str, str | None] = {machine.id: None for machine in sc.machines}
    shifts = sorted(pb.shifts, key=lambda s: (s.day, s.shift_id))
    tracker = SequencingTracker(ctx, debug=bool(debug))

    role_priority = build_role_priority(ctx)
    ordered_machines = sorted(
        sc.machines,
        key=lambda m: (role_priority.get(bundle.machine_roles.get(m.id) or "", 999), m.id),
    )

    for shift in shifts:
        day = shift.day
        shift_id = shift.shift_id
        used = {landing.id: 0 for landing in sc.landings}
        for machine in ordered_machines:
            block_id = sched.plan[machine.id][(day, shift_id)]
            lock_key = (machine.id, day)

            if (
                shift_availability.get((machine.id, day, shift_id), 1) == 0
                or availability.get((machine.id, day), 1) == 0
            ):
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

            if block_id is None:
                continue

            role = bundle.machine_roles.get(machine.id)
            allowed = allowed_roles.get(block_id)
            if allowed is not None and role is not None and role not in allowed:
                penalty += 1000.0
                continue

            earliest, latest = windows[block_id]
            if day < earliest or day > latest:
                penalty += 1000.0
                continue

            rate_value = rate.get((machine.id, block_id), 0.0)
            if rate_value <= 0.0:
                penalty += 1000.0
                continue

            sequencing = tracker.process(day, machine.id, block_id, rate_value)
            if sequencing.violation_reason:
                penalty += 1000.0

            landing_id = landing_of.get(block_id)
            if landing_id is not None and landing_id in used:
                used[landing_id] += 1
                capacity = max(landing_cap.get(landing_id, 0), 0)
                excess = max(0, used[landing_id] - capacity)
                if excess > 0:
                    if weights.landing_slack == 0.0:
                        penalty += 1000.0
                        continue
                    landing_slack_total += excess

            production_total += sequencing.production_units
            if sequencing.production_units <= BLOCK_COMPLETION_EPS:
                previous_block[machine.id] = block_id
                continue

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
                if prev_blk is not None and block_id != prev_blk:
                    transition_count += 1.0

            previous_block[machine.id] = block_id

    tracker.finalize()
    completion_bonus = sum(
        initial_work_required[block_id]
        for block_id, remaining_work in tracker.remaining_work.items()
        if remaining_work <= BLOCK_COMPLETION_EPS
    )
    leftover_total = sum(
        remaining_work
        for remaining_work in tracker.remaining_work.values()
        if remaining_work > BLOCK_COMPLETION_EPS
    )
    partial_weight = weights.production * PARTIAL_PRODUCTION_FRACTION
    score = (weights.production * (completion_bonus - LEFTOVER_PENALTY_FACTOR * leftover_total)) + (
        partial_weight * production_total
    )
    score -= weights.mobilisation * mobilisation_total
    score -= weights.transitions * transition_count
    score -= weights.landing_slack * landing_slack_total
    score -= penalty
    if debug is not None:
        debug_stats = tracker.debug_snapshot()
        debug_stats.update(
            {
                "production_total": production_total,
                "completion_bonus": completion_bonus,
                "leftover_total": leftover_total,
                "landing_slack_total": landing_slack_total,
                "penalty_total": penalty,
            }
        )
        debug.update(debug_stats)
    return score


def evaluate_schedule_with_debug(
    pb: Problem,
    sched: Schedule,
    ctx: OperationalProblem,
    capture_debug: bool,
) -> tuple[float, dict[str, Any] | None]:
    """Evaluate a schedule and optionally capture sequencing debug statistics."""

    debug_map: dict[str, Any] | None = {} if capture_debug else None
    score = evaluate_schedule(pb, sched, ctx, debug=debug_map)
    return score, debug_map


def build_watch_metadata_from_debug(stats: Mapping[str, Any] | None) -> dict[str, str]:
    """Convert sequencing debug stats into watch-friendly metadata."""

    if not stats:
        return {}
    meta: dict[str, str] = {}
    violation_count = stats.get("sequencing_violation_count")
    if violation_count is not None:
        meta["seq_violation_count"] = str(int(violation_count))
    status = stats.get("sequencing_status")
    if status:
        meta["seq_status"] = str(status)
    role = stats.get("sequencing_first_violation_role")
    if role:
        meta["seq_first_role"] = str(role)
    reason = stats.get("sequencing_first_violation_reason")
    if reason:
        meta["seq_first_reason"] = str(reason)
    block = stats.get("sequencing_first_violation_block")
    if block:
        meta["seq_first_block"] = str(block)
    day = stats.get("sequencing_first_violation_day")
    if day is not None:
        meta["seq_first_day"] = str(int(day))
    deficit = stats.get("sequencing_first_violation_headstart_deficit")
    if deficit is None:
        deficit = stats.get("sequencing_first_violation_deficit")
    if deficit is not None:
        meta["seq_first_deficit"] = f"{float(deficit):.3f}"
    breakdown = stats.get("sequencing_violation_breakdown")
    if breakdown:
        meta["seq_violation_breakdown"] = json.dumps(breakdown, sort_keys=True)
    return meta


def generate_neighbors(
    pb: Problem,
    sched: Schedule,
    registry: OperatorRegistry,
    rng,
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
        if all(math.isclose(w, weight_values[0]) for w in weight_values):
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
            _repair_schedule_cover_blocks(pb, candidate, ctx, fill_voids=False)
            neighbours.append(candidate)
            stats["accepted"] += 1.0
            if limit is not None and len(neighbours) >= limit:
                break
        else:
            stats.setdefault("skipped", 0.0)
            stats["skipped"] += 1.0
    return neighbours


def evaluate_candidates(
    pb: Problem,
    candidates: list[Schedule],
    ctx: OperationalProblem,
    max_workers: int | None = None,
) -> list[tuple[Schedule, float]]:
    """Evaluate candidate schedules, optionally in parallel, returning (schedule, score)."""

    if not candidates:
        return []
    if max_workers is None or max_workers <= 1 or len(candidates) == 1:
        return [(candidate, evaluate_schedule(pb, candidate, ctx)) for candidate in candidates]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        def _score(schedule: Schedule) -> float:
            return evaluate_schedule(pb, schedule, ctx)

        scores = list(executor.map(_score, candidates))
    return list(zip(candidates, scores))
