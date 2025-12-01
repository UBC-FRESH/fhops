"""Shared schedule helpers for heuristics (greedy seed, evaluation, neighbours)."""

from __future__ import annotations

import json
import math
from bisect import insort
from collections import defaultdict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from fhops.evaluation.sequencing import SequencingTracker, build_role_priority
from fhops.optimization.heuristics.registry import OperatorContext, OperatorRegistry
from fhops.optimization.operational_problem import OperationalProblem
from fhops.scenario.contract import Problem

BLOCK_COMPLETION_EPS = 1e-6
LEFTOVER_PENALTY_FACTOR = 1.0
AUTO_OBJECTIVE_WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {
    "FHOPS Tiny7": {
        "production": 1.0,
        "mobilisation": 0.2,
        "transitions": 0.1,
        "landing_slack": 0.05,
    },
    "FHOPS Small21": {
        "production": 1.0,
        "mobilisation": 0.2,
        "transitions": 0.1,
        "landing_slack": 0.05,
    },
}


def resolve_objective_weight_overrides(
    pb: Problem,
    overrides: dict[str, float] | None,
) -> dict[str, float] | None:
    """Return explicit overrides or scenario-specific defaults for objective weights."""

    if overrides is not None:
        return overrides
    scenario_name = getattr(pb.scenario, "name", None)
    if scenario_name:
        return AUTO_OBJECTIVE_WEIGHT_OVERRIDES.get(scenario_name)
    return None


@dataclass(slots=True)
class SlotProduction:
    """Cached production deltas contributed by a single slot assignment."""

    block_id: str
    role: str | None
    block_volume: float = 0.0
    role_volume: float = 0.0


@dataclass(slots=True)
class Schedule:
    """Machine assignment plan storing both dict and array views."""

    plan: dict[str, dict[tuple[int, str], str | None]]
    matrix: dict[str, list[str | None]] = field(default_factory=dict)
    mobilisation_cache: dict[str, MobilisationStats] = field(default_factory=dict)
    dirty_machines: set[str] = field(default_factory=set)
    block_remaining_cache: dict[str, float] | None = None
    role_remaining_cache: dict[tuple[str, str], float] | None = None
    dirty_blocks: set[str] = field(default_factory=set)
    block_slots: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    dirty_slots: set[tuple[str, int, str]] = field(default_factory=set)
    slot_production: dict[tuple[str, int, str], SlotProduction] = field(default_factory=dict)
    watch_stats: dict[str, Any] | None = None


@dataclass(slots=True)
class MobilisationStats:
    """Per-machine mobilisation bookkeeping."""

    cost: float = 0.0
    transitions: float = 0.0


def _ensure_machine_matrix(
    schedule: Schedule, machine_id: str, ctx: OperationalProblem
) -> list[str | None]:
    """Return (and lazily build) the dense shift array for a machine."""

    row = schedule.matrix.get(machine_id)
    if row is not None and len(row) == len(ctx.shift_keys):
        return row
    assignments = schedule.plan.setdefault(machine_id, {})
    row = [assignments.get(key) for key in ctx.shift_keys]
    schedule.matrix[machine_id] = row
    return row


def _ensure_block_slots(schedule: Schedule, ctx: OperationalProblem) -> None:
    """Populate block-to-slot ordering if it has not been built yet."""

    if schedule.block_slots:
        return
    slots: dict[str, list[tuple[int, str]]] = {}
    for machine_id, assignments in schedule.plan.items():
        for key, block_id in assignments.items():
            if block_id is None:
                continue
            shift_idx = ctx.shift_index[key]
            slots.setdefault(block_id, []).append((shift_idx, machine_id))
    for entries in slots.values():
        entries.sort()
    schedule.block_slots = slots


def _set_assignment(
    schedule: Schedule,
    machine_id: str,
    day: int,
    shift_id: str,
    block_id: str | None,
    ctx: OperationalProblem,
    *,
    mark_dirty: bool = True,
) -> None:
    """Keep plan + matrix in sync for a single slot update."""

    _ensure_block_slots(schedule, ctx)
    assignments = schedule.plan.setdefault(machine_id, {})
    key = (day, shift_id)
    old_block = assignments.get(key)
    if old_block == block_id:
        return
    assignments[key] = block_id
    row = _ensure_machine_matrix(schedule, machine_id, ctx)
    shift_idx = ctx.shift_index[key]
    row[shift_idx] = block_id
    if old_block is not None:
        entries = schedule.block_slots.get(old_block)
        if entries is not None:
            try:
                entries.remove((shift_idx, machine_id))
            except ValueError:
                pass
            if not entries:
                schedule.block_slots.pop(old_block, None)
    if block_id is not None:
        entries = schedule.block_slots.setdefault(block_id, [])
        insort(entries, (shift_idx, machine_id))
    if mark_dirty:
        if old_block and old_block != block_id:
            schedule.dirty_blocks.add(old_block)
        if block_id and block_id != old_block:
            schedule.dirty_blocks.add(block_id)
        schedule.dirty_slots.add((machine_id, day, shift_id))
    schedule.dirty_machines.add(machine_id)


def _build_matrix(
    plan: Mapping[str, Mapping[tuple[int, str], str | None]], ctx: OperationalProblem
) -> dict[str, list[str | None]]:
    """Materialize the dense matrix view from the plan."""

    return {
        machine_id: [assignments.get(key) for key in ctx.shift_keys]
        for machine_id, assignments in plan.items()
    }


def _recompute_mobilisation_for(
    schedule: Schedule,
    machine_id: str,
    ctx: OperationalProblem,
) -> None:
    """Recompute mobilisation stats for a single machine."""

    params = ctx.mobilisation_params.get(machine_id)
    row = _ensure_machine_matrix(schedule, machine_id, ctx)
    distance_lookup = ctx.distance_lookup
    cost = 0.0
    transitions = 0.0
    prev_block: str | None = None
    for block_id in row:
        if block_id is None:
            continue
        if prev_block is None:
            prev_block = block_id
            continue
        if block_id == prev_block:
            continue
        transitions += 1.0
        if params is not None:
            distance = distance_lookup.get((prev_block, block_id), 0.0)
            move_cost = params.setup_cost
            if distance <= params.walk_threshold_m:
                move_cost += params.walk_cost_per_meter * distance
            else:
                move_cost += params.move_cost_flat
            cost += move_cost
        prev_block = block_id
    schedule.mobilisation_cache[machine_id] = MobilisationStats(cost=cost, transitions=transitions)
    schedule.dirty_machines.discard(machine_id)


def _ensure_mobilisation_stats(schedule: Schedule, ctx: OperationalProblem) -> None:
    """Ensure mobilisation cache entries exist for all machines (recomputing dirty ones)."""

    if not schedule.mobilisation_cache and not schedule.dirty_machines:
        schedule.dirty_machines = set(schedule.plan.keys())
    for machine_id in list(schedule.dirty_machines):
        _recompute_mobilisation_for(schedule, machine_id, ctx)


def _release_slot_production(
    schedule: Schedule,
    machine_id: str,
    day: int,
    shift_id: str,
    block_remaining: dict[str, float],
    role_remaining: dict[tuple[str, str], float],
) -> None:
    """Restore cached production deltas for a slot back into the demand caches."""

    key = (machine_id, day, shift_id)
    contribution = schedule.slot_production.pop(key, None)
    if contribution is None:
        return
    if contribution.block_volume > 0.0:
        block_remaining[contribution.block_id] = (
            block_remaining.get(contribution.block_id, 0.0) + contribution.block_volume
        )
    if contribution.role and contribution.role_volume > 0.0:
        role_key = (contribution.block_id, contribution.role)
        role_remaining[role_key] = role_remaining.get(role_key, 0.0) + contribution.role_volume


def _store_slot_production(
    schedule: Schedule,
    machine_id: str,
    day: int,
    shift_id: str,
    block_id: str,
    role: str | None,
    block_volume: float,
    role_volume: float,
) -> None:
    """Persist the latest production deltas for a slot assignment."""

    key = (machine_id, day, shift_id)
    if block_volume <= BLOCK_COMPLETION_EPS and role_volume <= BLOCK_COMPLETION_EPS:
        schedule.slot_production.pop(key, None)
        return
    schedule.slot_production[key] = SlotProduction(
        block_id=block_id,
        role=role,
        block_volume=block_volume,
        role_volume=role_volume,
    )


def _repair_schedule_cover_blocks(
    pb: Problem,
    sched: Schedule,
    ctx: OperationalProblem,
    *,
    fill_voids: bool = True,
    limit_to_dirty_slots: bool = False,
    repair_stats: dict[str, float] | None = None,
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
    if limit_to_dirty_slots:
        block_remaining = sched.block_remaining_cache
        if block_remaining is None:
            block_remaining = dict(ctx.bundle.work_required)
            sched.block_remaining_cache = block_remaining
        role_remaining = sched.role_remaining_cache
        if role_remaining is None:
            role_remaining = dict(ctx.role_work_required)
            sched.role_remaining_cache = role_remaining
    else:
        block_remaining = dict(ctx.bundle.work_required)
        role_remaining = dict(ctx.role_work_required)
        sched.block_remaining_cache = block_remaining
        sched.role_remaining_cache = role_remaining
        sched.slot_production.clear()
    block_system = bundle.block_system
    explicit_blocks = ctx.blocks_with_explicit_system
    prereq_roles = ctx.prereq_roles
    role_headstarts = ctx.role_headstarts
    role_priority = build_role_priority(ctx)

    shift_keys = ctx.shift_keys

    plan = sched.plan
    for machine in sc.machines:
        machine_plan = plan.setdefault(machine.id, {})
        for key in shift_keys:
            machine_plan.setdefault(key, None)
        _ensure_machine_matrix(sched, machine.id, ctx)
    _ensure_block_slots(sched, ctx)

    dirty_blocks = (
        set(sched.dirty_blocks) if sched.dirty_blocks else set(bundle.work_required.keys())
    )
    if not dirty_blocks:
        return

    def set_assignment(machine_id: str, day: int, shift_id: str, block_id: str | None) -> None:
        _set_assignment(sched, machine_id, day, shift_id, block_id, ctx, mark_dirty=False)

    block_machine_index: defaultdict[str, set[str]] = defaultdict(set)
    for (machine_id, block_id), rate_value in rate.items():
        if rate_value > 0.0:
            block_machine_index[block_id].add(machine_id)

    machines_to_visit: set[str] = set()
    if not limit_to_dirty_slots:
        machines_to_visit = set(plan.keys())
    else:
        for block_id in dirty_blocks:
            machines_to_visit.update(block_machine_index.get(block_id, ()))
            for _, machine_id in sched.block_slots.get(block_id, []):
                machines_to_visit.add(machine_id)
        if not machines_to_visit:
            machines_to_visit = set(plan.keys())
    dirty_slots: set[tuple[str, int, str]] = set()
    slots_to_process: dict[tuple[int, str], set[str]] = {}
    machines_touched: set[str] = set()
    if limit_to_dirty_slots:
        dirty_slots.update(sched.dirty_slots)
        for block_id in dirty_blocks:
            for shift_idx, machine_id in sched.block_slots.get(block_id, []):
                day_slot, shift_slot = shift_keys[shift_idx]
                dirty_slots.add((machine_id, day_slot, shift_slot))
        for machine_id, day_slot, shift_slot in dirty_slots:
            _release_slot_production(
                sched,
                machine_id,
                day_slot,
                shift_slot,
                block_remaining,
                role_remaining,
            )
            slots_to_process.setdefault((day_slot, shift_slot), set()).add(machine_id)
    processed_slots: set[tuple[str, int, str]] = set()
    slots_visited = 0

    if limit_to_dirty_slots and slots_to_process:
        shift_iteration: list[tuple[int, str]] = sorted(
            slots_to_process.keys(), key=lambda key: ctx.shift_index[key]
        )
    else:
        shift_iteration = list(shift_keys)

    ordered_machines = [machine for machine in sc.machines if machine.id in machines_to_visit]
    ordered_machines.sort(
        key=lambda m: (role_priority.get(machine_roles.get(m.id) or "", 999), m.id)
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

    def record_assignment(machine_id: str, day: int, shift_id: str, block_id: str) -> None:
        role = machine_roles.get(machine_id)
        production = compute_production(machine_id, block_id, role)
        slot_key = (machine_id, day, shift_id)
        if production <= BLOCK_COMPLETION_EPS:
            sched.slot_production.pop(slot_key, None)
            return
        block_delta = 0.0
        role_delta = 0.0
        if block_id in explicit_blocks and role is not None:
            prereqs = prereq_roles.get((block_id, role))
            if prereqs:
                for upstream in prereqs:
                    key = (block_id, upstream)
                    role_inventory_estimate[key] = max(
                        0.0, role_inventory_estimate.get(key, 0.0) - production
                    )
            role_inventory_today[(block_id, role)] += production
            role_key = (block_id, role)
            if role_key in role_remaining:
                role_remaining[role_key] = max(0.0, role_remaining.get(role_key, 0.0) - production)
                role_delta = production
            if is_terminal(block_id, role):
                block_remaining[block_id] = max(
                    0.0, block_remaining.get(block_id, 0.0) - production
                )
                block_delta = production
            role_counts_day[(block_id, role)] += 1
        else:
            block_remaining[block_id] = max(0.0, block_remaining.get(block_id, 0.0) - production)
            block_delta = production
        _store_slot_production(
            sched,
            machine_id,
            day,
            shift_id,
            block_id,
            role,
            block_delta,
            role_delta,
        )

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
                if (
                    role_name == role
                    and remaining > BLOCK_COMPLETION_EPS
                    and block_id in dirty_blocks
                ):
                    demand.append((block_id, remaining))
        for block_id, remaining in block_remaining.items():
            if remaining <= BLOCK_COMPLETION_EPS:
                continue
            if block_id not in dirty_blocks:
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

    for day, shift_id in shift_iteration:
        advance_day(day)
        if limit_to_dirty_slots:
            machines_for_slot = slots_to_process.get((day, shift_id))
            if not machines_for_slot:
                continue
            machine_iter = [
                machine for machine in ordered_machines if machine.id in machines_for_slot
            ]
            if not machine_iter:
                continue
        else:
            machine_iter = ordered_machines
        for machine in machine_iter:
            slots_visited += 1
            role = machine_roles.get(machine.id)
            slot_key = (day, shift_id)
            machine_plan = plan[machine.id]
            slot_block: str | None = machine_plan.get(slot_key)
            lock_block = locked.get((machine.id, day))
            locked_slot = lock_block is not None
            if locked_slot:
                slot_block = lock_block
                set_assignment(machine.id, day, shift_id, slot_block)
            if (
                limit_to_dirty_slots
                and not locked_slot
                and slot_block is not None
                and slot_block not in dirty_blocks
            ):
                record_assignment(machine.id, day, shift_id, slot_block)
                continue
            if shift_availability.get((machine.id, day, shift_id), 1) == 0:
                set_assignment(machine.id, day, shift_id, None)
                continue
            if availability.get((machine.id, day), 1) == 0:
                set_assignment(machine.id, day, shift_id, None)
                continue
            if (machine.id, day, shift_id) in blackout:
                set_assignment(machine.id, day, shift_id, None)
                continue
            if slot_block is not None and slot_block not in dirty_blocks and not locked_slot:
                continue
            if slot_block is not None:
                if not slot_is_valid(
                    machine.id,
                    day,
                    slot_block,
                    role,
                    enforce_prereq=not locked_slot,
                ):
                    slot_block = None
                    set_assignment(machine.id, day, shift_id, None)
            if slot_block is None and fill_voids:
                candidate = select_block(machine.id, day, shift_id, role)
                if candidate is None:
                    set_assignment(machine.id, day, shift_id, None)
                    continue
                set_assignment(machine.id, day, shift_id, candidate)
                slot_block = candidate
                machines_touched.add(machine.id)
            if slot_block is not None:
                record_assignment(machine.id, day, shift_id, slot_block)
                machines_touched.add(machine.id)
            if limit_to_dirty_slots:
                processed_slots.add((machine.id, day, shift_id))

    sched.dirty_blocks.difference_update(dirty_blocks)
    if limit_to_dirty_slots:
        if processed_slots:
            sched.dirty_slots.difference_update(processed_slots)
        if machines_touched:
            sched.dirty_machines.update(machines_touched)
    else:
        sched.dirty_slots.clear()
    if not fill_voids:
        sched.dirty_blocks.clear()
        return
    if repair_stats is not None:
        repair_stats["dirty_blocks"] = float(len(dirty_blocks))
        repair_stats["slots_visited"] = float(slots_visited)
        if limit_to_dirty_slots:
            repair_stats["slots_processed"] = float(len(processed_slots))
            repair_stats["machines_touched"] = float(len(machines_touched))
        else:
            repair_stats["slots_processed"] = float(slots_visited)


def init_greedy_schedule(pb: Problem, ctx: OperationalProblem) -> Schedule:
    """Construct an initial Schedule by greedily filling shifts with best-rate blocks."""

    sc = pb.scenario
    bundle = ctx.bundle
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
    block_remaining = dict(bundle.work_required)
    role_remaining = dict(ctx.role_work_required)

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
        return block_remaining.get(block_id, 0.0)

    shift_keys = ctx.shift_keys
    plan: dict[str, dict[tuple[int, str], str | None]] = {
        machine.id: {(day, shift_id): None for day, shift_id in shift_keys}
        for machine in sc.machines
    }
    matrix_rows: dict[str, list[str | None]] = {
        machine.id: [None for _ in ctx.shift_keys] for machine in sc.machines
    }
    slot_production: dict[tuple[str, int, str], SlotProduction] = {}

    def assign(machine_id: str, day: int, shift_id: str, block_id: str | None) -> None:
        plan[machine_id][(day, shift_id)] = block_id
        matrix_rows[machine_id][ctx.shift_index[(day, shift_id)]] = block_id
        if block_id is None:
            slot_production.pop((machine_id, day, shift_id), None)
            return
        role = machine_roles.get(machine_id)
        base_rate = rate.get((machine_id, block_id), 0.0)
        if base_rate <= 0.0:
            return
        block_delta = 0.0
        role_delta = 0.0
        if block_id in explicit_blocks and role is not None and (block_id, role) in role_remaining:
            production = min(base_rate, role_remaining[(block_id, role)])
            role_remaining[(block_id, role)] = max(
                0.0, role_remaining[(block_id, role)] - production
            )
            role_delta = production
            if _is_terminal(block_id, role):
                block_remaining[block_id] = max(0.0, block_remaining[block_id] - production)
                block_delta = production
        else:
            production = min(base_rate, block_remaining[block_id])
            block_remaining[block_id] = max(0.0, block_remaining[block_id] - production)
            block_delta = production
        if block_delta > BLOCK_COMPLETION_EPS or role_delta > BLOCK_COMPLETION_EPS:
            slot_production[(machine_id, day, shift_id)] = SlotProduction(
                block_id=block_id,
                role=role,
                block_volume=block_delta,
                role_volume=role_delta,
            )

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
            for day, shift_id in shift_keys:
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
                    break
        return best_slot

    # Respect locked assignments up front.
    for day, shift_id in shift_keys:
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
    for day, shift_id in shift_keys:
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
                if role is not None:
                    demand = role_remaining.get((block.id, role), 0.0)
                else:
                    demand = block_remaining.get(block.id, 0.0)
                if demand <= BLOCK_COMPLETION_EPS:
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
    schedule = Schedule(plan=plan, matrix=matrix_rows, slot_production=slot_production)
    _ensure_block_slots(schedule, ctx)
    schedule.block_remaining_cache = dict(block_remaining)
    schedule.role_remaining_cache = dict(role_remaining)
    schedule.dirty_machines = set(plan.keys())
    _ensure_mobilisation_stats(schedule, ctx)
    return schedule


def evaluate_schedule(
    pb: Problem,
    sched: Schedule,
    ctx: OperationalProblem,
    debug: dict[str, Any] | None = None,
    *,
    limit_repairs_to_dirty: bool = False,
) -> float:
    """Score a schedule using production, mobilisation, transition, and slack penalties."""

    repair_stats: dict[str, float] | None = {} if limit_repairs_to_dirty else None
    _repair_schedule_cover_blocks(
        pb,
        sched,
        ctx,
        limit_to_dirty_slots=limit_repairs_to_dirty,
        repair_stats=repair_stats,
    )

    sc = pb.scenario
    bundle = ctx.bundle
    rate = bundle.production_rates
    windows = bundle.windows
    landing_of = bundle.landing_for_block
    landing_cap = bundle.landing_capacity
    allowed_roles = ctx.allowed_roles
    blackout = ctx.blackout_shifts
    locked = ctx.locked_assignments
    shift_availability = bundle.availability_shift
    availability = bundle.availability_day

    weights = bundle.objective_weights

    _ensure_mobilisation_stats(sched, ctx)
    mobilisation_total = sum(stats.cost for stats in sched.mobilisation_cache.values())
    transition_count = sum(stats.transitions for stats in sched.mobilisation_cache.values())
    landing_slack_total = 0.0
    penalty = 0.0

    previous_block: dict[str, str | None] = {machine.id: None for machine in sc.machines}
    tracker = SequencingTracker(ctx, debug=bool(debug))

    role_priority = build_role_priority(ctx)
    ordered_machines = sorted(
        sc.machines,
        key=lambda m: (role_priority.get(bundle.machine_roles.get(m.id) or "", 999), m.id),
    )

    for day, shift_id in ctx.shift_keys:
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

            if sequencing.production_units <= BLOCK_COMPLETION_EPS:
                previous_block[machine.id] = block_id
                continue

            previous_block[machine.id] = block_id

    tracker.finalize()
    delivered_total = tracker.delivered_total
    leftover_total = sum(
        remaining_work
        for remaining_work in tracker.remaining_work.values()
        if remaining_work > BLOCK_COMPLETION_EPS
    )
    score = weights.production * (delivered_total - LEFTOVER_PENALTY_FACTOR * leftover_total)
    score -= weights.mobilisation * mobilisation_total
    score -= weights.transitions * transition_count
    score -= weights.landing_slack * landing_slack_total
    score -= penalty
    watch_stats: dict[str, Any] = {
        "delivered_total": delivered_total,
        "leftover_total": leftover_total,
        "landing_slack_total": landing_slack_total,
        "penalty_total": penalty,
    }
    if repair_stats:
        watch_stats.setdefault("repair_slots_processed", repair_stats.get("slots_processed", 0.0))
        watch_stats.setdefault("repair_slots_visited", repair_stats.get("slots_visited", 0.0))
        watch_stats.setdefault("repair_dirty_blocks", repair_stats.get("dirty_blocks", 0.0))
        watch_stats.setdefault("repair_machines_touched", repair_stats.get("machines_touched", 0.0))
    sched.watch_stats = watch_stats
    if debug is not None:
        debug_stats = tracker.debug_snapshot()
        debug_stats.update(watch_stats)
        debug.update(debug_stats)
    return score


def evaluate_schedule_with_debug(
    pb: Problem,
    sched: Schedule,
    ctx: OperationalProblem,
    capture_debug: bool,
    *,
    limit_repairs_to_dirty: bool = False,
) -> tuple[float, dict[str, Any] | None]:
    """Evaluate a schedule and optionally capture sequencing debug statistics."""

    debug_map: dict[str, Any] | None = {} if capture_debug else None
    score = evaluate_schedule(
        pb,
        sched,
        ctx,
        debug=debug_map,
        limit_repairs_to_dirty=limit_repairs_to_dirty,
    )
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
    remaining_total = stats.get("remaining_work_total")
    if remaining_total is not None:
        meta["staged_volume_m3"] = f"{float(remaining_total):.2f}"
    delivered_total = stats.get("delivered_total")
    if delivered_total is not None:
        meta["delivered_volume_m3"] = f"{float(delivered_total):.2f}"
    slots_processed = stats.get("repair_slots_processed")
    if slots_processed is not None:
        meta["repair_slots"] = f"{float(slots_processed):.0f}"
    dirty_blocks = stats.get("repair_dirty_blocks")
    if dirty_blocks is not None:
        meta["repair_blocks"] = f"{float(dirty_blocks):.0f}"
    completed_blocks = stats.get("completed_blocks")
    if completed_blocks is not None:
        meta["completed_blocks"] = str(int(completed_blocks))
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
        shift_keys=ctx.shift_keys,
        shift_index=ctx.shift_index,
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
    *,
    limit_repairs_to_dirty: bool = False,
) -> list[tuple[Schedule, float]]:
    """Evaluate candidate schedules, optionally in parallel, returning (schedule, score)."""

    if not candidates:
        return []
    if max_workers is None or max_workers <= 1 or len(candidates) == 1:
        return [
            (
                candidate,
                evaluate_schedule(
                    pb,
                    candidate,
                    ctx,
                    limit_repairs_to_dirty=limit_repairs_to_dirty,
                ),
            )
            for candidate in candidates
        ]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        def _score(schedule: Schedule) -> float:
            return evaluate_schedule(
                pb, schedule, ctx, limit_repairs_to_dirty=limit_repairs_to_dirty
            )

        scores = list(executor.map(_score, candidates))
    return list(zip(candidates, scores))
