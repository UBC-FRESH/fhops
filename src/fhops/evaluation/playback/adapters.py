"""Helpers to translate solver outputs into playback records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pandas as pd

from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import build_distance_lookup

from ..sequencing import build_role_order_lookup, build_role_priority, build_sequencing_tracker
from .core import PlaybackRecord

if TYPE_CHECKING:  # pragma: no cover
    from fhops.optimization.heuristics.sa import Schedule
else:  # pragma: no cover - runtime fallback
    Schedule = object

__all__ = [
    "schedule_to_records",
    "assignments_to_records",
]


def schedule_to_records(problem: Problem, schedule: Schedule) -> Iterator[PlaybackRecord]:
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

    tracker = build_sequencing_tracker(problem)
    machine_roles = tracker.ctx.bundle.machine_roles
    role_order_lookup = build_role_order_lookup(tracker.ctx)
    role_priority = build_role_priority(tracker.ctx)

    def _role_sort_value(row: pd.Series) -> int:
        block_val = row.get("block_id")
        machine_val = row.get("machine_id")
        if pd.isna(block_val) or pd.isna(machine_val):
            return 999
        block_id = str(block_val)
        role = machine_roles.get(str(machine_val))
        role_key = role if role is not None else ""
        return role_order_lookup.get((block_id, role_key), role_priority.get(role_key, 999))

    df["_role_order"] = df.apply(_role_sort_value, axis=1)
    df = df.sort_values(["day", "shift_id", "_role_order", "machine_id", "block_id"]).reset_index(
        drop=True
    )
    df = df.drop(columns=["_role_order"])

    scenario = problem.scenario
    rate = {(r.machine_id, r.block_id): r.rate for r in scenario.production_rates}
    remaining = tracker.remaining_work
    machine_hours = {machine.id: machine.daily_hours for machine in scenario.machines}

    shift_hours_map: dict[str, float] = {}
    if scenario.timeline and scenario.timeline.shifts:
        shift_hours_map = {
            shift_def.name: shift_def.hours for shift_def in scenario.timeline.shifts
        }

    mobilisation = scenario.mobilisation
    mobilisation_lookup = build_distance_lookup(mobilisation) if mobilisation else {}
    mobilisation_params = (
        {param.machine_id: param for param in mobilisation.machine_params}
        if mobilisation is not None
        else {}
    )
    previous_block: dict[str, str | None] = defaultdict(lambda: None)

    landing_lookup = {block.id: block.landing_id for block in scenario.blocks}

    blackout_days: set[int] = set()
    if scenario.timeline and scenario.timeline.blackouts:
        for blackout in scenario.timeline.blackouts:
            blackout_days.update(range(blackout.start_day, blackout.end_day + 1))

    def hours_for(machine_id: str, shift_id: str) -> tuple[float | None, str | None]:
        if shift_id in shift_hours_map:
            return shift_hours_map[shift_id], "shift_definition"
        hours = machine_hours.get(machine_id)
        if hours is not None:
            return hours, "machine_daily_hours"
        return None, None

    def production_for(machine_id: str, block_id: str, proposed: float | None) -> tuple[float, str]:
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
        for _, row in df.iterrows():
            machine_id = str(row["machine_id"])
            block_id = row.get("block_id")
            if pd.isna(block_id):
                continue
            block_id = str(block_id)
            day = int(row["day"])
            shift_id = str(row.get("shift_id", "S1"))

            proposed_production = None
            if "production" in row and not pd.isna(row["production"]):
                proposed_production = float(row["production"])

            production_units, production_source = production_for(
                machine_id, block_id, proposed_production
            )
            hours_worked, hours_source = hours_for(machine_id, shift_id)
            mobilisation_value = mobilisation_cost(machine_id, block_id)

            metadata: dict[str, object] = {}
            if hours_source:
                metadata["hours_source"] = hours_source
            metadata["production_source"] = production_source
            landing_id = landing_lookup.get(block_id)
            if landing_id is not None:
                metadata["landing_id"] = landing_id

            sequencing = tracker.process(day, machine_id, block_id, production_units)
            production_units = sequencing.production_units
            role = sequencing.machine_role
            if sequencing.violation_reason:
                metadata["sequencing_violation"] = sequencing.violation_reason
            if sequencing.block_completed:
                metadata["block_completed"] = True

            blackout_hit = day in blackout_days
            downtime_flag = bool(row.get("_downtime", 0))
            weather_severity_value = row.get("_weather_severity")
            if pd.notna(weather_severity_value) and weather_severity_value != 0:
                weather_severity = float(weather_severity_value)
            else:
                weather_severity = None

            yield PlaybackRecord(
                day=day,
                shift_id=shift_id,
                machine_id=machine_id,
                block_id=block_id,
                hours_worked=hours_worked,
                production_units=production_units,
                mobilisation_cost=mobilisation_value,
                blackout_hit=blackout_hit,
                landing_id=landing_id,
                machine_role=role,
                downtime=downtime_flag,
                weather_severity=weather_severity,
                metadata=metadata,
            )
        tracker.finalize()

    return iter_records()
