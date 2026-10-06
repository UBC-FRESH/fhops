"""Helpers to translate solver outputs into playback records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

import pandas as pd

from fhops.scenario.contract import Problem, Scenario
from fhops.scheduling.mobilisation import build_distance_lookup

from ..sequencing import (
    SequencingTracker,
    build_role_order_lookup,
    build_role_priority,
    build_sequencing_tracker,
)
from .core import PlaybackRecord

if TYPE_CHECKING:  # pragma: no cover
    from fhops.optimization.heuristics.sa import Schedule
else:  # pragma: no cover - runtime fallback
    Schedule = object

__all__ = [
    "schedule_to_records",
    "assignments_to_records",
]


def shift_hours_resolver(
    scenario: Scenario,
) -> Callable[[str, str], tuple[float | None, str | None]]:
    """Build the lookup playback uses to assign hours to a machine-shift.

    Parameters
    ----------
    scenario : fhops.scenario.contract.Scenario
        Scenario providing optional ``timeline.shifts`` definitions and machine ``daily_hours``.

    Returns
    -------
    Callable[[str, str], tuple[float | None, str | None]]
        Function ``(machine_id, shift_id) -> (hours, source)``. ``hours`` is the
        ``ShiftDefinition.hours`` of the matching timeline shift (``source="shift_definition"``),
        otherwise the machine's ``daily_hours`` (``source="machine_daily_hours"``), otherwise
        ``(None, None)``.

    Notes
    -----
    Deterministic playback (``hours_worked``) and the stochastic downtime event share this
    rule so sampled downtime hours and recorded hours stay on the same scale.
    """

    machine_hours = {machine.id: machine.daily_hours for machine in scenario.machines}
    shift_hours_map: dict[str, float] = {}
    if scenario.timeline and scenario.timeline.shifts:
        shift_hours_map = {
            shift_def.name: shift_def.hours for shift_def in scenario.timeline.shifts
        }

    def hours_for(machine_id: str, shift_id: str) -> tuple[float | None, str | None]:
        if shift_id in shift_hours_map:
            return shift_hours_map[shift_id], "shift_definition"
        hours = machine_hours.get(machine_id)
        if hours is not None:
            return hours, "machine_daily_hours"
        return None, None

    return hours_for


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
    """Convert solver assignments dataframe into playback records.

    Parameters
    ----------
    problem : fhops.scenario.contract.Problem
        Problem wrapping the scenario being replayed.
    assignments : pandas.DataFrame
        Rows with ``machine_id``, ``block_id``, ``day`` and optional ``shift_id`` (default
        ``"S1"``), ``assigned`` (rows with ``assigned <= 0`` are skipped) and ``production``
        (volume, m³; when missing the production rate capped by remaining work is used).
        Stochastic events may add the private columns ``_downtime`` (flag),
        ``_downtime_hours`` (sampled downtime hours) and ``_weather_severity``.

    Returns
    -------
    Iterator[PlaybackRecord]
        Iterator exposing the ``sequencing_tracker`` used to cap production.

    Notes
    -----
    Rows flagged by downtime keep their record even when the whole shift is lost
    (``assigned == 0``): such records carry ``production_units = 0``, ``hours_worked = 0``
    and ``downtime_hours`` equal to the lost shift hours, and they bypass the sequencing
    tracker and mobilisation costing (the machine did not work). Partially lost shifts report
    ``hours_worked = shift_hours - downtime_hours``.
    """

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
        keep = df["assigned"] > 0
        if "_downtime" in df.columns:
            keep |= df["_downtime"].fillna(0).astype(bool)
        df = df[keep]

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
    hours_for = shift_hours_resolver(scenario)

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
            downtime_value = row.get("_downtime", 0)
            downtime_flag = bool(pd.notna(downtime_value) and downtime_value)
            downtime_hours: float | None = None
            raw_downtime_hours = row.get("_downtime_hours")
            if downtime_flag and raw_downtime_hours is not None and pd.notna(raw_downtime_hours):
                downtime_hours = float(raw_downtime_hours)
            cancelled = False
            if downtime_flag:
                assigned_value = row.get("assigned", 1)
                cancelled = bool(pd.notna(assigned_value) and float(assigned_value) <= 0)

            if cancelled:
                shift_hours, hours_source = hours_for(machine_id, shift_id)
                landing_id = landing_lookup.get(block_id)
                cancelled_metadata: dict[str, object] = {
                    "production_source": "downtime",
                    "downtime_full_shift": True,
                }
                if hours_source:
                    cancelled_metadata["hours_source"] = hours_source
                if landing_id is not None:
                    cancelled_metadata["landing_id"] = landing_id
                yield PlaybackRecord(
                    day=day,
                    shift_id=shift_id,
                    machine_id=machine_id,
                    block_id=block_id,
                    hours_worked=0.0 if shift_hours is not None else None,
                    production_units=0.0,
                    mobilisation_cost=None,
                    blackout_hit=False,
                    landing_id=landing_id,
                    machine_role=machine_roles.get(machine_id),
                    downtime=True,
                    weather_severity=None,
                    metadata=cancelled_metadata,
                    downtime_hours=downtime_hours if downtime_hours is not None else shift_hours,
                )
                continue

            proposed_production = None
            if "production" in row and not pd.isna(row["production"]):
                proposed_production = float(row["production"])

            production_units, production_source = production_for(
                machine_id, block_id, proposed_production
            )
            hours_worked, hours_source = hours_for(machine_id, shift_id)
            if downtime_flag and downtime_hours is not None and hours_worked is not None:
                hours_worked = max(hours_worked - downtime_hours, 0.0)
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
                downtime_hours=downtime_hours,
            )
        tracker.finalize()

    class RecordIterator:
        def __init__(self, iterator: Iterator[PlaybackRecord], tracker: SequencingTracker) -> None:
            self._iterator = iterator
            self.sequencing_tracker = tracker

        def __iter__(self) -> RecordIterator:
            return self

        def __next__(self) -> PlaybackRecord:
            return next(self._iterator)

    return RecordIterator(iter_records(), tracker)
