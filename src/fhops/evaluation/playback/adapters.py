"""Helpers to translate solver outputs into playback records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pandas as pd

from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import build_distance_lookup

from ..sequencing import (
    SequencingTracker,
    build_role_order_lookup,
    build_role_priority,
    build_sequencing_tracker,
)
from .core import PlaybackRecord, shift_hours_resolver

if TYPE_CHECKING:  # pragma: no cover
    from fhops.optimization.heuristics.sa import Schedule
else:  # pragma: no cover - runtime fallback
    Schedule = object

__all__ = [
    "schedule_to_records",
    "assignments_to_records",
    "DEFAULT_SHIFT_ID",
    "multi_shift_days",
    "normalise_shift_ids",
    "shift_hours_resolver",
]

DEFAULT_SHIFT_ID = "S1"
"""Shift label assumed for assignment rows without ``shift_id`` in single-shift scenarios."""


def multi_shift_days(problem: Problem) -> list[int]:
    """Return the days on which the problem has more than one shift slot.

    Parameters
    ----------
    problem : fhops.scenario.contract.Problem
        Problem whose ``shifts`` (built from ``shift_calendar``, else ``timeline.shifts``, else one
        ``S1`` shift per day) define the slot grid. A day counts as multi-shift when any machine
        (or the timeline) has two or more distinct shift IDs on it.

    Returns
    -------
    list[int]
        Sorted days with at least two distinct shift IDs (empty for single-shift scenarios).
    """

    per_day: dict[int, set[str]] = defaultdict(set)
    for shift in problem.shifts:
        per_day[int(shift.day)].add(str(shift.shift_id))
    return sorted(day for day, shifts in per_day.items() if len(shifts) > 1)


def normalise_shift_ids(problem: Problem, assignments: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``assignments`` with a string ``shift_id`` column.

    Parameters
    ----------
    problem : fhops.scenario.contract.Problem
        Problem being replayed.
    assignments : pandas.DataFrame
        Assignment rows; ``shift_id`` is optional only for single-shift scenarios.

    Returns
    -------
    pandas.DataFrame
        Copy with ``shift_id`` filled: missing column or missing values become
        :data:`DEFAULT_SHIFT_ID` (``"S1"``) when every day has a single shift.

    Raises
    ------
    ValueError
        When the scenario has more than one shift on some day (:func:`multi_shift_days`) and an
        active row (``assigned > 0``, or every row without an ``assigned`` column) has no
        ``shift_id`` (missing column or missing value). Replaying such rows as ``"S1"`` would
        silently collapse every shift of the day onto the first one (FHOPS 1.0.0 behaviour).
        Inactive rows are filled with ``"S1"`` without error.
    """

    df = assignments.copy()
    if "assigned" in df.columns:
        active = df["assigned"].fillna(0) > 0
    else:
        active = pd.Series(True, index=df.index)
    missing_column = "shift_id" not in df.columns
    if missing_column:
        missing_rows = int(active.sum())
    else:
        missing_rows = int((df["shift_id"].isna() & active).sum())
    if missing_rows:
        days = multi_shift_days(problem)
        if days:
            what = (
                "has no shift_id column"
                if missing_column
                else f"has {missing_rows} row(s) without shift_id"
            )
            preview = ", ".join(str(day) for day in days[:5])
            more = ", ..." if len(days) > 5 else ""
            raise ValueError(
                f"assignments {what}, but scenario '{problem.scenario.name}' has more than one "
                f"shift per day (days {preview}{more}); provide shift_id for every row "
                f"(solver outputs include it)."
            )
    if missing_column:
        df["shift_id"] = DEFAULT_SHIFT_ID
    df["shift_id"] = df["shift_id"].fillna(DEFAULT_SHIFT_ID).astype(str)
    return df


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
        Rows with ``machine_id``, ``block_id``, ``day``, ``shift_id`` (optional only for
        single-shift scenarios, default ``"S1"``; see :func:`normalise_shift_ids`), ``assigned``
        (rows with ``assigned <= 0`` are skipped) and ``production`` (volume, m³; when missing
        the production rate capped by remaining work is used). The frame index is ignored.
        Stochastic events may add the private columns ``_downtime`` (flag),
        ``_downtime_hours`` (sampled downtime hours), ``_downtime_lost`` (proposed volume
        removed by downtime, m³), ``_weather_severity`` and ``_weather_lost`` (proposed volume
        removed by weather, m³).

    Returns
    -------
    Iterator[PlaybackRecord]
        Iterator over chronologically ordered records. The iterator exposes a
        ``sequencing_tracker`` attribute holding the :class:`SequencingTracker` used to cap
        production.

    Raises
    ------
    ValueError
        When required columns are missing, or when the scenario has several shifts per day and a
        replayed row has no ``shift_id`` (:func:`normalise_shift_ids`).

    Notes
    -----
    Rows flagged by downtime keep their record even when the whole shift is lost
    (``assigned == 0``): such records carry ``production_units = 0``, ``hours_worked = 0``
    and ``downtime_hours`` equal to the lost shift hours, and they bypass the sequencing
    tracker and mobilisation costing (the machine did not work). Partially lost shifts report
    ``hours_worked = shift_hours - downtime_hours``. ``shift_hours`` comes from
    :func:`shift_hours_resolver`. When the private ``_downtime_lost`` / ``_weather_lost`` columns
    are present, their values are copied to ``metadata["downtime_production_lost"]`` /
    ``metadata["weather_production_lost"]`` (m³) for record-level loss KPIs.

    When ``Scenario.initial_state`` is set, the sequencing tracker starts from the carried-in
    staged inventory, role remaining volumes, and role shift counts, and each machine's
    mobilisation tracking starts at its ``last_block_id`` so the first move to a different block
    is charged (matching the operational MILP and the heuristics).

    An empty plan (``assignments`` is ``None``, has no rows, or has no row with
    ``assigned > 0``) yields no records but still exposes a fresh ``sequencing_tracker``, so
    callers see the full ``Block.work_required`` as remaining and nothing delivered. Empty
    frames are accepted without the required-column check.
    """

    tracker = build_sequencing_tracker(problem)
    if assignments is None or assignments.empty:
        return _RecordIterator(iter(()), tracker)

    required = {"machine_id", "block_id", "day"}
    missing = required - set(assignments.columns)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"assignments missing required columns: {missing_str}")

    df = assignments.reset_index(drop=True)
    if "assigned" in df.columns:
        keep = df["assigned"] > 0
        if "_downtime" in df.columns:
            keep |= df["_downtime"].fillna(0).astype(bool)
        df = df[keep]
    if df.empty:
        return _RecordIterator(iter(()), tracker)
    df = normalise_shift_ids(problem, df)

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

    shift_index = tracker.ctx.shift_index
    unknown_slot = len(shift_index)

    def _slot_sort_value(row: pd.Series) -> int:
        return shift_index.get((int(row["day"]), str(row["shift_id"])), unknown_slot)

    df["_role_order"] = df.apply(_role_sort_value, axis=1)
    df["_slot_order"] = df.apply(_slot_sort_value, axis=1)
    # Slots replay in the problem's shift order (the operational MILP's prev(s)), not label order.
    df = df.sort_values(
        ["day", "_slot_order", "shift_id", "_role_order", "machine_id", "block_id"]
    ).reset_index(drop=True)
    df = df.drop(columns=["_role_order", "_slot_order"])

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
    previous_block.update(tracker.ctx.initial_machine_block)

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
            shift_id = str(row["shift_id"])
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
                shift_hours, hours_source = hours_for(machine_id, shift_id, day)
                landing_id = landing_lookup.get(block_id)
                cancelled_metadata: dict[str, object] = {
                    "production_source": "downtime",
                    "downtime_full_shift": True,
                }
                if hours_source:
                    cancelled_metadata["hours_source"] = hours_source
                if landing_id is not None:
                    cancelled_metadata["landing_id"] = landing_id
                _copy_lost_volumes(row, cancelled_metadata)
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
            hours_worked, hours_source = hours_for(machine_id, shift_id, day)
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
            _copy_lost_volumes(row, metadata)

            sequencing = tracker.process(day, machine_id, block_id, production_units, shift_id)
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

    return _RecordIterator(iter_records(), tracker)


_LOST_VOLUME_COLUMNS = (
    ("_downtime_lost", "downtime_production_lost"),
    ("_weather_lost", "weather_production_lost"),
)


def _copy_lost_volumes(row: pd.Series, metadata: dict[str, object]) -> None:
    """Copy event-recorded lost volumes (m³) from private columns into record metadata."""

    for column, key in _LOST_VOLUME_COLUMNS:
        value = row.get(column)
        if value is not None and pd.notna(value) and float(value) > 0.0:
            metadata[key] = float(value)


class _RecordIterator:
    """Record iterator exposing the :class:`SequencingTracker` that capped its production."""

    def __init__(self, iterator: Iterator[PlaybackRecord], tracker: SequencingTracker) -> None:
        self._iterator = iterator
        self.sequencing_tracker = tracker

    def __iter__(self) -> _RecordIterator:
        return self

    def __next__(self) -> PlaybackRecord:
        return next(self._iterator)
