"""Helpers to translate solver outputs into playback records."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterator

import pandas as pd

from fhops.scheduling.mobilisation import build_distance_lookup
from fhops.scenario.contract import Problem

from .core import PlaybackRecord

try:  # pragma: no cover - optional import for typing
    from fhops.optimization.heuristics.sa import Schedule
except ImportError:  # pragma: no cover - fallback when heuristics not available
    Schedule = object  # type: ignore[assignment]

__all__ = [
    "schedule_to_records",
    "assignments_to_records",
]


def schedule_to_records(problem: Problem, schedule: "Schedule") -> Iterator[PlaybackRecord]:
    """Convert a heuristic `Schedule` plan into playback records."""

    rows: list[dict[str, object]] = []
    for machine_id, plan in getattr(schedule, "plan", {}).items():
        for (day, shift_id), block_id in plan.items():
            if block_id is None:
                continue
            rows.append(
                {
                    "machine_id": machine_id,
                    "block_id": block_id,
                    "day": int(day),
                    "shift_id": shift_id,
                    "assigned": 1,
                }
            )
    frame = pd.DataFrame(rows, columns=["machine_id", "block_id", "day", "shift_id", "assigned"])
    return assignments_to_records(problem, frame)


def assignments_to_records(problem: Problem, assignments: pd.DataFrame) -> Iterator[PlaybackRecord]:
    """Convert solver assignments dataframe into playback records."""

    if assignments is None or assignments.empty:
        return iter(())

    required = {"machine_id", "block_id", "day"}
    missing = required - set(assignments.columns)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"assignments missing required columns: {missing_str}")

    df = assignments.copy()
    if "shift_id" not in df.columns:
        df["shift_id"] = "S1"
    df["shift_id"] = df["shift_id"].fillna("S1").astype(str)
    if "assigned" in df.columns:
        df = df[df["assigned"] > 0]

    df = df.sort_values(["day", "shift_id", "machine_id", "block_id"]).reset_index(drop=True)

    scenario = problem.scenario
    rate = {(r.machine_id, r.block_id): r.rate for r in scenario.production_rates}
    remaining = {block.id: block.work_required for block in scenario.blocks}
    machine_hours = {machine.id: machine.daily_hours for machine in scenario.machines}
    allowed_roles, prereq_roles, machine_roles = _system_metadata(problem)

    shift_hours_map: dict[str, float] = {}
    if scenario.timeline and scenario.timeline.shifts:
        shift_hours_map = {shift_def.name: shift_def.hours for shift_def in scenario.timeline.shifts}

    mobilisation = scenario.mobilisation
    mobilisation_lookup = build_distance_lookup(mobilisation) if mobilisation else {}
    mobilisation_params = (
        {param.machine_id: param for param in mobilisation.machine_params}
        if mobilisation is not None
        else {}
    )
    previous_block: dict[str, str | None] = defaultdict(lambda: None)

    blackout_days: set[int] = set()
    if scenario.timeline and scenario.timeline.blackouts:
        for blackout in scenario.timeline.blackouts:
            blackout_days.update(range(blackout.start_day, blackout.end_day + 1))

    completed_blocks: set[str] = set()
    seq_cumulative: defaultdict[tuple[str, str], int] = defaultdict(int)
    day_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    current_day: int | None = None

    def hours_for(machine_id: str, shift_id: str) -> tuple[float | None, str | None]:
        if shift_id in shift_hours_map:
            return shift_hours_map[shift_id], "shift_definition"
        hours = machine_hours.get(machine_id)
        if hours is not None:
            return hours, "machine_daily_hours"
        return None, None

    def production_for(
        machine_id: str, block_id: str, proposed: float | None
    ) -> tuple[float, str]:
        if proposed is not None:
            value = max(proposed, 0.0)
            return value, "column"
        rate_value = rate.get((machine_id, block_id), 0.0)
        block_remaining = remaining.get(block_id, 0.0)
        production = min(rate_value, block_remaining)
        return production, "rate"

    def mobilisation_cost(machine_id: str, block_id: str) -> float | None:
        params = mobilisation_params.get(machine_id)
        if params is None:
            return None
        previous = previous_block[machine_id]
        previous_block[machine_id] = block_id
        if previous is None or previous == block_id:
            return None
        distance = mobilisation_lookup.get((previous, block_id), 0.0)
        cost = params.setup_cost
        if distance <= params.walk_threshold_m:
            cost += params.walk_cost_per_meter * distance
        else:
            cost += params.move_cost_flat
        return cost

    def iter_records() -> Iterator[PlaybackRecord]:
        nonlocal current_day, day_counts, seq_cumulative
        for _, row in df.iterrows():
            machine_id = str(row["machine_id"])
            block_id = row.get("block_id")
            if pd.isna(block_id):
                continue
            block_id = str(block_id)
            day = int(row["day"])
            shift_id = str(row.get("shift_id", "S1"))

            if current_day is None:
                current_day = day
            elif day != current_day:
                for key, count in day_counts.items():
                    seq_cumulative[key] += count
                day_counts.clear()
                current_day = day

            proposed_production = None
            if "production" in row and not pd.isna(row["production"]):
                proposed_production = float(row["production"])

            production_units, production_source = production_for(
                machine_id, block_id, proposed_production
            )
            if block_id in remaining:
                remaining[block_id] = max(0.0, remaining[block_id] - production_units)

            hours_worked, hours_source = hours_for(machine_id, shift_id)
            mobilisation_value = mobilisation_cost(machine_id, block_id)

            metadata: dict[str, object] = {}
            if hours_source:
                metadata["hours_source"] = hours_source
            metadata["production_source"] = production_source

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
                    required = seq_cumulative[(block_id, role)] + day_counts[(block_id, role)] + 1
                    available = min(
                        seq_cumulative[(block_id, prereq)] + day_counts[(block_id, prereq)]
                        for prereq in prereqs
                    )
                    if available < required:
                        violation_reason = "missing_prereq"

            if role is not None:
                day_counts[(block_id, role)] += 1

            if violation_reason is not None:
                metadata["sequencing_violation"] = violation_reason

            if block_id in remaining and remaining[block_id] <= 1e-6 and block_id not in completed_blocks:
                completed_blocks.add(block_id)
                metadata["block_completed"] = True

            blackout_hit = day in blackout_days

            yield PlaybackRecord(
                day=day,
                shift_id=shift_id,
                machine_id=machine_id,
                block_id=block_id,
                hours_worked=hours_worked,
                production_units=production_units,
                mobilisation_cost=mobilisation_value,
                blackout_hit=blackout_hit,
                metadata=metadata,
            )

    return iter_records()


def _system_metadata(pb: Problem):
    scenario = pb.scenario
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
    return allowed, prereqs, machine_roles
