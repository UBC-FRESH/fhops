"""KPI helpers for FHOPS schedules."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pandas as pd

from fhops.evaluation.playback.aggregates import DAY_SUMMARY_COLUMNS, SHIFT_SUMMARY_COLUMNS
from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import build_distance_lookup

from .aggregates import compute_makespan_metrics, compute_utilisation_metrics

__all__ = ["KPIResult", "compute_kpis"]


@dataclass(slots=True)
class KPIResult(Mapping[str, float | int | str]):
    """Structured KPI bundle with optional shift/day calendar attachments."""

    totals: dict[str, float | int | str] = field(default_factory=dict)
    shift_calendar: pd.DataFrame | None = None
    day_calendar: pd.DataFrame | None = None

    SHIFT_COLUMNS: ClassVar[tuple[str, ...]] = tuple(SHIFT_SUMMARY_COLUMNS)
    DAY_COLUMNS: ClassVar[tuple[str, ...]] = tuple(DAY_SUMMARY_COLUMNS)

    def __post_init__(self) -> None:
        if self.shift_calendar is not None:
            missing = set(self.SHIFT_COLUMNS) - set(self.shift_calendar.columns)
            if missing:
                raise ValueError(f"Shift calendar missing columns: {sorted(missing)}")
            self.shift_calendar = self.shift_calendar.reindex(columns=self.SHIFT_COLUMNS).copy()
        if self.day_calendar is not None:
            missing = set(self.DAY_COLUMNS) - set(self.day_calendar.columns)
            if missing:
                raise ValueError(f"Day calendar missing columns: {sorted(missing)}")
            self.day_calendar = self.day_calendar.reindex(columns=self.DAY_COLUMNS).copy()

    # Mapping interface -------------------------------------------------
    def __getitem__(self, key: str) -> float | int | str:
        return self.totals[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.totals)

    def __len__(self) -> int:
        return len(self.totals)

    def get(self, key: str, default: Any = None) -> Any:
        return self.totals.get(key, default)

    # Convenience helpers -----------------------------------------------
    def to_dict(self) -> dict[str, float | int | str]:
        """Return the scalar KPI totals as a plain dictionary."""

        return dict(self.totals)

    def with_calendars(
        self,
        *,
        shift_calendar: pd.DataFrame | None = None,
        day_calendar: pd.DataFrame | None = None,
    ) -> KPIResult:
        """Return a copy with the provided calendars attached."""

        return KPIResult(
            totals=self.to_dict(),
            shift_calendar=shift_calendar if shift_calendar is not None else self.shift_calendar,
            day_calendar=day_calendar if day_calendar is not None else self.day_calendar,
        )


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


def compute_kpis(pb: Problem, assignments: pd.DataFrame) -> KPIResult:
    """Compute production, mobilisation, utilisation, and sequencing KPIs from assignments."""

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
    mobilisation_by_machine: dict[str, float] = defaultdict(float)
    landing_lookup = {block.id: block.landing_id for block in sc.blocks}
    mobilisation_by_landing: dict[str, float] = defaultdict(float)

    allowed_roles, prereq_roles, machine_roles = _system_metadata(pb)
    system_blocks = {block.id for block in sc.blocks if block.harvest_system_id}
    seq_cumulative: defaultdict[tuple[str, str], int] = defaultdict(int)
    seq_violations = 0
    seq_violation_blocks: set[str] = set()
    seq_violation_days: set[tuple[str, int]] = set()
    seq_reason_counts: Counter[str] = Counter()

    total_prod = 0.0
    days_with_work: set[int] = set()
    shift_keys_with_work: set[tuple[int, str]] = set()
    sorted_assignments = assignments.sort_values(["day", "machine_id", "block_id"])
    for day in sorted_assignments["day"].drop_duplicates().sort_values():
        day = int(day)
        day_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        day_rows = sorted_assignments[sorted_assignments["day"] == day]
        for _, row in day_rows.iterrows():
            machine_id = row["machine_id"]
            block_id = row["block_id"]
            shift_id = (
                row["shift_id"] if "shift_id" in row and not pd.isna(row["shift_id"]) else "S1"
            )
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
            if production > 0:
                days_with_work.add(day)
                shift_keys_with_work.add((day, str(shift_id)))

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
                mobilisation_by_machine[machine_id] += cost
                landing_id = landing_lookup.get(block_id)
                if landing_id:
                    mobilisation_by_landing[landing_id] += cost
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
        if mobilisation_by_machine:
            result["mobilisation_cost_by_machine"] = json.dumps(
                {
                    machine: round(cost, 3)
                    for machine, cost in sorted(mobilisation_by_machine.items())
                }
            )
        if mobilisation_by_landing:
            result["mobilisation_cost_by_landing"] = json.dumps(
                {
                    landing: round(cost, 3)
                    for landing, cost in sorted(mobilisation_by_landing.items())
                }
            )

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
    non_default_repairs = [
        machine.id
        for machine in pb.scenario.machines
        if getattr(machine, "repair_usage_hours", None) not in (None, 10000)
    ]
    if non_default_repairs:
        result["repair_usage_alert"] = ", ".join(sorted(non_default_repairs))
    from fhops.evaluation.playback import PlaybackConfig, run_playback
    from fhops.evaluation.playback.aggregates import day_dataframe, shift_dataframe

    playback_result = run_playback(pb, assignments, config=PlaybackConfig())
    shift_df = shift_dataframe(playback_result)
    day_df = day_dataframe(playback_result)

    utilisation_metrics = compute_utilisation_metrics(shift_df, day_df)
    result.update(utilisation_metrics)

    makespan_metrics = compute_makespan_metrics(
        pb,
        shift_df,
        fallback_days=days_with_work,
        fallback_shift_keys=shift_keys_with_work,
    )
    result.update(makespan_metrics)

    total_hours_recorded = float(shift_df.get("total_hours", pd.Series(dtype=float)).sum())
    avg_production_rate = (total_prod / total_hours_recorded) if total_hours_recorded > 0 else 0.0

    if "downtime_hours" in shift_df.columns:
        total_downtime_hours = float(shift_df["downtime_hours"].sum())
        if total_downtime_hours > 0:
            result["downtime_hours_total"] = total_downtime_hours
            result["downtime_production_loss_est"] = total_downtime_hours * avg_production_rate
        downtime_by_machine = shift_df.groupby("machine_id", dropna=False)["downtime_hours"].sum()
        downtime_by_machine = downtime_by_machine[downtime_by_machine > 0]
        if not downtime_by_machine.empty:
            result["downtime_hours_by_machine"] = json.dumps(
                {
                    machine: round(float(hours), 3)
                    for machine, hours in sorted(downtime_by_machine.items())
                }
            )
        downtime_events_series = shift_df.get("downtime_events")
        total_downtime_events = (
            int(float(downtime_events_series.sum())) if downtime_events_series is not None else 0
        )
        if total_downtime_events > 0:
            result["downtime_event_count"] = total_downtime_events

    if "weather_severity_total" in shift_df.columns:
        total_weather_severity = float(shift_df["weather_severity_total"].sum())
        if total_weather_severity > 0:
            result["weather_severity_total"] = total_weather_severity
            # Approximate weather impact by scaling total affected severity with average shift hours.
            average_shift_hours = (
                (total_hours_recorded / len(shift_df)) if len(shift_df) > 0 else 0.0
            )
            weather_hours_est = total_weather_severity * average_shift_hours
            result["weather_hours_est"] = weather_hours_est
            result["weather_production_loss_est"] = weather_hours_est * avg_production_rate
        weather_by_machine = shift_df.groupby("machine_id", dropna=False)[
            "weather_severity_total"
        ].sum()
        weather_by_machine = weather_by_machine[weather_by_machine > 0]
        if not weather_by_machine.empty:
            result["weather_severity_by_machine"] = json.dumps(
                {
                    machine: round(float(value), 3)
                    for machine, value in sorted(weather_by_machine.items())
                }
            )

    return KPIResult(totals=result, shift_calendar=shift_df, day_calendar=day_df)
