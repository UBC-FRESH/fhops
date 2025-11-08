"""Simulated annealing heuristic for FHOPS."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import pandas as pd

from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import MachineMobilisation, build_distance_lookup


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


def _blackout_map(scenario) -> set[tuple[str, int]]:
    blackout: set[tuple[str, int]] = set()
    timeline = getattr(scenario, "timeline", None)
    if timeline and timeline.blackouts:
        for blackout_window in timeline.blackouts:
            for day in range(blackout_window.start_day, blackout_window.end_day + 1):
                for machine in scenario.machines:
                    blackout.add((machine.id, day))
    return blackout


def _locked_map(scenario) -> dict[tuple[str, int], str]:
    locks = getattr(scenario, "locked_assignments", None)
    if not locks:
        return {}
    return {(lock.machine_id, lock.day): lock.block_id for lock in locks}


__all__ = ["Schedule", "solve_sa"]


@dataclass(slots=True)
class Schedule:
    """Machine assignment plan keyed by machine/day."""

    plan: dict[str, dict[int, str | None]]


def _init_greedy(pb: Problem) -> Schedule:
    sc = pb.scenario
    remaining = {block.id: block.work_required for block in sc.blocks}
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    windows = {block_id: sc.window_for(block_id) for block_id in sc.block_ids()}
    allowed_roles, prereq_roles, machine_roles, _ = _role_metadata(sc)
    blackout = _blackout_map(sc)
    locked = _locked_map(sc)

    plan: dict[str, dict[int, str | None]] = {
        machine.id: {day: None for day in pb.days} for machine in sc.machines
    }

    for day in pb.days:
        for machine in sc.machines:
            if availability.get((machine.id, day), 1) == 0:
                continue
            lock_key = (machine.id, day)
            if lock_key in locked:
                plan[machine.id][day] = locked[lock_key]
                continue
            if lock_key in blackout:
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
                plan[machine.id][day] = best_block
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
    for day in sorted(pb.days):
        used = {landing.id: 0 for landing in sc.landings}
        day_role_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        for machine in sc.machines:
            block_id = sched.plan[machine.id][day]
            if block_id is None:
                if (machine.id, day) in locked:
                    penalty += 1000.0
                continue
            if (machine.id, day) in blackout:
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
                required = role_cumulative[role_key] + day_role_counts[role_key] + 1
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
                day_role_counts[(block_id, role)] += 1
        for key, count in day_role_counts.items():
            role_cumulative[key] += count
    score = prod_weight * production_total
    score -= mobil_weight * mobilisation_total
    score -= transition_weight * transition_count
    score -= landing_slack_weight * landing_slack_total
    score -= penalty
    return score


def _neighbors(pb: Problem, sched: Schedule) -> list[Schedule]:
    sc = pb.scenario
    machines = [machine.id for machine in sc.machines]
    days = list(pb.days)
    if not machines or not days:
        return []
    allowed_roles, _, machine_roles, _ = _role_metadata(sc)
    blackout = _blackout_map(sc)
    locked = _locked_map(sc)

    # swap two machines on a day
    eligible_days = [d for d in days if sum((m, d) not in locked for m in machines) >= 2]
    if eligible_days:
        day = random.choice(eligible_days)
        free_machines = [m for m in machines if (m, day) not in locked]
        m1, m2 = random.sample(free_machines, k=2)
    else:
        day = days[0]
        m1, m2 = (machines[0], machines[0])
    swap_plan = {m: plan.copy() for m, plan in sched.plan.items()}
    swap_plan[m1][day], swap_plan[m2][day] = swap_plan[m2][day], swap_plan[m1][day]
    neighbours = [Schedule(plan=swap_plan)]
    # move assignment within a machine across days
    machine = random.choice(machines)
    free_days = [d for d in days if (machine, d) not in locked]
    if len(free_days) >= 2:
        d1, d2 = random.sample(free_days, k=2)
    elif free_days:
        d1 = d2 = free_days[0]
    else:
        d1 = d2 = days[0]
    move_plan = {m: plan.copy() for m, plan in sched.plan.items()}
    move_plan[machine][d2] = move_plan[machine][d1]
    move_plan[machine][d1] = None
    neighbours.append(Schedule(plan=move_plan))

    sanitized: list[Schedule] = []
    for neighbour in neighbours:
        plan: dict[str, dict[int, str | None]] = {}
        for mach, assignments in neighbour.plan.items():
            role = machine_roles.get(mach)
            plan[mach] = {}
            for day_key, blk in assignments.items():
                allowed = allowed_roles.get(blk) if blk is not None else None
                if (mach, day_key) in locked:
                    plan[mach][day_key] = locked[(mach, day_key)]
                elif blk is not None and (
                    (mach, day_key) in blackout or (allowed is not None and role not in allowed)
                ):
                    plan[mach][day_key] = None
                else:
                    plan[mach][day_key] = blk
        sanitized.append(Schedule(plan=plan))
    return sanitized


def solve_sa(pb: Problem, iters: int = 2000, seed: int = 42) -> dict[str, Any]:
    """Run simulated annealing returning objective and assignments DataFrame."""
    random.seed(seed)
    current = _init_greedy(pb)
    current_score = _evaluate(pb, current)
    best = current
    best_score = current_score

    temperature0 = max(1.0, best_score / 10.0)
    temperature = temperature0
    for step in range(1, iters + 1):
        accepted = False
        for neighbor in _neighbors(pb, current):
            neighbor_score = _evaluate(pb, neighbor)
            delta = neighbor_score - current_score
            if delta >= 0 or random.random() < math.exp(delta / max(temperature, 1e-6)):
                current = neighbor
                current_score = neighbor_score
                accepted = True
                break
        if current_score > best_score:
            best, best_score = current, current_score
        temperature = temperature0 * (0.995**step)
        if not accepted and step % 100 == 0:
            current = _init_greedy(pb)
            current_score = _evaluate(pb, current)

    rows = []
    for machine_id, plan in best.plan.items():
        for day, block_id in plan.items():
            if block_id is not None:
                rows.append(
                    {"machine_id": machine_id, "block_id": block_id, "day": int(day), "assigned": 1}
                )
    assignments = pd.DataFrame(rows).sort_values(["day", "machine_id", "block_id"])
    return {"objective": float(best_score), "assignments": assignments}
