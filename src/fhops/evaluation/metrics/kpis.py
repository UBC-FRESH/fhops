"""KPI helpers for FHOPS schedules."""

from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import build_distance_lookup

__all__ = ["compute_kpis"]


def _system_metadata(pb: Problem):
    sc = pb.scenario
    systems = sc.harvest_systems or {}
    allowed: dict[str, set[str] | None] = {}
    prereqs: dict[tuple[str, str], set[str]] = {}
    for block in sc.blocks:
        system = systems.get(block.harvest_system_id) if block.harvest_system_id else None
        if not system:
            allowed[block.id] = None
            continue
        job_roles = {job.name: job.machine_role for job in system.jobs}
        allowed[block.id] = {job.machine_role for job in system.jobs}
        for job in system.jobs:
            prereq_roles = {job_roles[name] for name in job.prerequisites if name in job_roles}
            if prereq_roles:
                prereqs[(block.id, job.machine_role)] = prereq_roles
    machine_roles = {machine.id: getattr(machine, "role", None) for machine in sc.machines}
    return allowed, prereqs, machine_roles


def compute_kpis(pb: Problem, assignments: pd.DataFrame) -> dict[str, float | int | str]:
    """Compute production, mobilisation, and sequencing KPIs from assignments."""

    sc = pb.scenario
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    remaining = {block.id: block.work_required for block in sc.blocks}

    mobilisation_cost = 0.0
    mobilisation = sc.mobilisation
    mobilisation_lookup = build_distance_lookup(mobilisation)
    mobil_params = (
        {param.machine_id: param for param in mobilisation.machine_params}
        if mobilisation is not None
        else {}
    )
    previous_block: dict[str, str | None] = {machine.id: None for machine in sc.machines}

    allowed_roles, prereq_roles, machine_roles = _system_metadata(pb)
    system_blocks = {block.id for block in sc.blocks if block.harvest_system_id}
    seq_cumulative: defaultdict[tuple[str, str], int] = defaultdict(int)
    seq_violations = 0
    seq_violation_blocks: set[str] = set()
    seq_violation_days: set[tuple[str, int]] = set()
    seq_reason_counts: Counter[str] = Counter()

    total_prod = 0.0
    sorted_assignments = assignments.sort_values(["day", "machine_id", "block_id"])
    for day in sorted_assignments["day"].drop_duplicates().sort_values():
        day = int(day)
        day_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        day_rows = sorted_assignments[sorted_assignments["day"] == day]
        for _, row in day_rows.iterrows():
            machine_id = row["machine_id"]
            block_id = row["block_id"]
            role = machine_roles.get(machine_id)
            allowed = allowed_roles.get(block_id)

            violation_reason: str | None = None
            if allowed is not None and role is None:
                violation_reason = "unknown_role"
            elif allowed is not None and role not in allowed:
                violation_reason = "forbidden_role"
            elif role is not None:
                prereqs = prereq_roles.get((block_id, role))
                if prereqs:
                    role_key = (block_id, role)
                    required = seq_cumulative[role_key] + day_counts[role_key] + 1
                    available = min(seq_cumulative[(block_id, prereq)] for prereq in prereqs)
                    if available < required:
                        violation_reason = "missing_prereq"

            if violation_reason is not None:
                seq_violations += 1
                seq_violation_blocks.add(block_id)
                seq_violation_days.add((block_id, day))
                seq_reason_counts[violation_reason] += 1

            if role is not None:
                day_counts[(block_id, role)] += 1

            production = min(rate.get((machine_id, block_id), 0.0), remaining[block_id])
            remaining[block_id] = max(0.0, remaining[block_id] - production)
            total_prod += production

            params = mobil_params.get(machine_id)
            prev = previous_block.get(machine_id)
            if params is not None and prev is not None and prev != block_id:
                distance = mobilisation_lookup.get((prev, block_id), 0.0)
                cost = params.setup_cost
                if distance <= params.walk_threshold_m:
                    cost += params.walk_cost_per_meter * distance
                else:
                    cost += params.move_cost_flat
                mobilisation_cost += cost
            previous_block[machine_id] = block_id

        for (blk, role), count in day_counts.items():
            seq_cumulative[(blk, role)] += count

    completed_blocks = sum(1 for rem in remaining.values() if rem <= 1e-6)

    result: dict[str, float | int | str] = {
        "total_production": total_prod,
        "completed_blocks": float(completed_blocks),
    }
    if mobilisation is not None:
        result["mobilisation_cost"] = mobilisation_cost

    if system_blocks:
        result["sequencing_violation_count"] = seq_violations
        result["sequencing_violation_blocks"] = len(seq_violation_blocks)
        result["sequencing_violation_days"] = len(seq_violation_days)
        clean_blocks = max(len(system_blocks) - len(seq_violation_blocks), 0)
        result["sequencing_clean_blocks"] = clean_blocks
        result["sequencing_violation_breakdown"] = (
            ", ".join(f"{reason}={count}" for reason, count in sorted(seq_reason_counts.items()))
            if seq_reason_counts
            else "none"
        )
    return result
