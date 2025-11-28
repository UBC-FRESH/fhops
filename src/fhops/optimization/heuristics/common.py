"""Shared schedule helpers for heuristics (greedy seed, evaluation, neighbours)."""

from __future__ import annotations

import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

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


def init_greedy_schedule(pb: Problem, ctx: OperationalProblem) -> Schedule:
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


def evaluate_schedule(pb: Problem, sched: Schedule, ctx: OperationalProblem) -> float:
    """Score a schedule using production, mobilisation, transition, and slack penalties."""

    sc = pb.scenario
    bundle = ctx.bundle
    remaining = dict(bundle.work_required)
    rate = bundle.production_rates
    windows = bundle.windows
    landing_of = bundle.landing_for_block
    landing_cap = bundle.landing_capacity
    mobil_params = dict(ctx.mobilisation_params)
    distance_lookup = ctx.distance_lookup

    allowed_roles = ctx.allowed_roles
    prereq_roles = ctx.prereq_roles
    machine_roles = bundle.machine_roles
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
    unfinished_block: dict[str, str | None] = {machine.id: None for machine in sc.machines}
    role_cumulative: defaultdict[tuple[str, str], int] = defaultdict(int)
    shifts = sorted(pb.shifts, key=lambda s: (s.day, s.shift_id))

    def assigned_blocks_snapshot() -> set[str]:
        return {
            block_id
            for machine_plan in sched.plan.values()
            for block_id in machine_plan.values()
            if block_id is not None
        }

    def select_alternate_block(
        machine_id: str,
        day: int,
        shift_id: str,
        excluded: set[str] | None = None,
    ) -> str | None:
        role = machine_roles.get(machine_id)
        best_block: str | None = None
        best_rate = 0.0
        assigned_now = assigned_blocks_snapshot()
        unassigned_candidates: list[str] = []
        fallback_candidates: list[str] = []
        for block in sc.blocks:
            block_id = block.id
            if excluded and block_id in excluded:
                continue
            remaining_work = remaining[block_id]
            if remaining_work <= BLOCK_COMPLETION_EPS:
                continue
            earliest, latest = windows[block_id]
            if day < earliest or day > latest:
                continue
            allowed = allowed_roles.get(block_id)
            if allowed is not None and role is not None and role not in allowed:
                continue
            r = rate.get((machine_id, block_id), 0.0)
            if r <= 0.0:
                continue
            target_list = (
                unassigned_candidates if block_id not in assigned_now else fallback_candidates
            )
            target_list.append((r, block_id))
        candidate_pool = unassigned_candidates or fallback_candidates
        if not candidate_pool:
            return None
        candidate_pool.sort(reverse=True, key=lambda item: item[0])
        _, best_block = candidate_pool[0]
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
            attempted_blocks: set[str] = set()
            while True:
                auto_selected = False
                if block_id is None:
                    block_id = select_alternate_block(
                        machine.id, day, shift_id, excluded=attempted_blocks
                    )
                    if block_id is None:
                        break
                    sched.plan[machine.id][(day, shift_id)] = block_id
                    auto_selected = True

                allowed = allowed_roles.get(block_id)
                role: str | None = machine_roles.get(machine.id)
                if allowed is not None and role is not None and role not in allowed:
                    if auto_selected:
                        attempted_blocks.add(block_id)
                        block_id = None
                        continue
                    penalty += 1000.0
                    previous_block[machine.id] = None
                    block_id = None
                    break
                prereq_set = prereq_roles.get((block_id, role)) if role is not None else None
                if prereq_set:
                    assert role is not None
                    role_key = (block_id, role)
                    available_units = min(
                        role_cumulative[(block_id, prereq)] for prereq in prereq_set
                    )
                    required_units = role_cumulative[role_key] + shift_role_counts[role_key] + 1
                    if required_units > available_units:
                        if auto_selected:
                            attempted_blocks.add(block_id)
                            block_id = None
                            continue
                        penalty += 1000.0
                        previous_block[machine.id] = block_id
                        block_id = None
                        break
                earliest, latest = windows[block_id]
                if day < earliest or day > latest:
                    attempted_blocks.add(block_id)
                    block_id = select_alternate_block(
                        machine.id, day, shift_id, excluded=attempted_blocks
                    )
                    if block_id is None:
                        break
                    sched.plan[machine.id][(day, shift_id)] = block_id
                    auto_selected = True
                    continue
                if remaining[block_id] <= 1e-9:
                    attempted_blocks.add(block_id)
                    alternate = select_alternate_block(
                        machine.id, day, shift_id, excluded=attempted_blocks
                    )
                    if alternate is None:
                        break
                    block_id = alternate
                    sched.plan[machine.id][(day, shift_id)] = block_id
                    auto_selected = True
                    continue
                break

            if block_id is None:
                continue
            landing_id = landing_of[block_id]
            capacity = landing_cap[landing_id]
            next_usage = used[landing_id] + 1
            excess = max(0, next_usage - capacity)
            if excess > 0:
                if weights.landing_slack == 0.0:
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
    partial_weight = weights.production * PARTIAL_PRODUCTION_FRACTION
    score = (weights.production * (completion_bonus - LEFTOVER_PENALTY_FACTOR * leftover_total)) + (
        partial_weight * production_total
    )
    score -= weights.mobilisation * mobilisation_total
    score -= weights.transitions * transition_count
    score -= weights.landing_slack * landing_slack_total
    score -= penalty
    return score


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
