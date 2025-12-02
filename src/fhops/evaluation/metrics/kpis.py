"""KPI helpers for FHOPS schedules."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pandas as pd

from fhops.evaluation.playback import PlaybackConfig, run_playback
from fhops.evaluation.playback.aggregates import (
    DAY_SUMMARY_COLUMNS,
    SHIFT_SUMMARY_COLUMNS,
    day_dataframe,
    shift_dataframe,
)
from fhops.evaluation.sequencing import build_role_priority
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem

from .aggregates import compute_makespan_metrics, compute_utilisation_metrics

__all__ = ["KPIResult", "compute_kpis"]


@dataclass(slots=True)
class KPIResult(Mapping[str, float | int | str]):
    """Structured KPI bundle with optional shift/day calendar attachments."""

    totals: dict[str, float | int | str] = field(default_factory=dict)
    shift_calendar: pd.DataFrame | None = None
    day_calendar: pd.DataFrame | None = None
    sequencing_debug: dict[str, object] | None = None

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


def compute_kpis(pb: Problem, assignments: pd.DataFrame) -> KPIResult:
    """Compute production, mobilisation, utilisation, and sequencing KPIs from assignments."""

    playback_result = run_playback(pb, assignments, config=PlaybackConfig())
    shift_df = shift_dataframe(playback_result)
    day_df = day_dataframe(playback_result)

    delivered_total = getattr(playback_result, "delivered_total", None)
    remaining_work_total = getattr(playback_result, "remaining_work_total", None)

    sc = pb.scenario
    total_required = sum(block.work_required for block in sc.blocks)

    mobilisation_cost = 0.0
    mobilisation_by_machine: dict[str, float] = defaultdict(float)
    mobilisation_by_landing: dict[str, float] = defaultdict(float)
    fallback_prod = 0.0
    completed_blocks: set[str] = set()
    seq_violation_events = 0
    seq_violation_blocks: set[str] = set()
    seq_violation_days: set[tuple[str, int]] = set()
    seq_reason_counts: Counter[str] = Counter()

    for record in playback_result.records:
        production = float(record.production_units or 0.0)
        fallback_prod += production
        if record.mobilisation_cost:
            cost = float(record.mobilisation_cost)
            mobilisation_cost += cost
            mobilisation_by_machine[record.machine_id] += cost
            landing_id = record.metadata.get("landing_id") or record.landing_id
            if landing_id is not None:
                mobilisation_by_landing[str(landing_id)] += cost
        if record.metadata.get("block_completed") and record.block_id:
            completed_blocks.add(record.block_id)
        violation = record.metadata.get("sequencing_violation")
        if violation and record.block_id:
            seq_violation_events += 1
            seq_violation_blocks.add(record.block_id)
            seq_violation_days.add((record.block_id, record.day))
            seq_reason_counts[str(violation)] += 1

    if delivered_total is None:
        delivered_total = fallback_prod
    result: dict[str, float | int | str] = {
        "total_production": float(delivered_total),
        "completed_blocks": float(len(completed_blocks)),
    }
    if remaining_work_total is not None:
        staged_volume = float(remaining_work_total)
        residual = float(total_required - float(delivered_total))
        if residual >= 0 and abs(staged_volume - residual) <= 1e-6:
            staged_volume = residual
        if abs(staged_volume) <= 1e-6:
            staged_volume = 0.0
        result["staged_production"] = staged_volume
        result["remaining_work_total"] = staged_volume
        adjusted_total = float(total_required) - staged_volume
        if adjusted_total >= 0:
            result["total_production"] = adjusted_total
    if mobilisation_cost > 0:
        result["mobilisation_cost"] = mobilisation_cost
        result["mobilisation_cost_by_machine"] = json.dumps(
            {machine: round(cost, 3) for machine, cost in sorted(mobilisation_by_machine.items())}
        )
        result["mobilisation_cost_by_landing"] = json.dumps(
            {landing: round(cost, 3) for landing, cost in sorted(mobilisation_by_landing.items())}
        )

    system_blocks = {block.id for block in sc.blocks if block.harvest_system_id}
    if system_blocks:
        result["sequencing_violation_count"] = seq_violation_events
        result["sequencing_violation_blocks"] = len(seq_violation_blocks)
        result["sequencing_violation_days"] = len(seq_violation_days)
        clean_blocks = max(len(system_blocks - seq_violation_blocks), 0)
        result["sequencing_clean_blocks"] = clean_blocks
        result["sequencing_violation_breakdown"] = (
            ", ".join(f"{reason}={count}" for reason, count in sorted(seq_reason_counts.items()))
            if seq_reason_counts
            else "none"
        )

    non_default_repairs = [
        machine.id
        for machine in sc.machines
        if getattr(machine, "repair_usage_hours", None) not in (None, 10000)
    ]
    if non_default_repairs:
        result["repair_usage_alert"] = ", ".join(sorted(non_default_repairs))

    ctx = build_operational_problem(pb)
    utilisation_metrics = compute_utilisation_metrics(shift_df, day_df)
    role_metric = utilisation_metrics.get("utilisation_ratio_by_role")
    if role_metric:
        role_priority = build_role_priority(ctx)
        ordered_payload = json.loads(role_metric)
        ordered_items = sorted(
            ordered_payload.items(),
            key=lambda item: (role_priority.get(item[0], 999), item[0]),
        )
        utilisation_metrics["utilisation_ratio_by_role"] = json.dumps(
            {role: value for role, value in ordered_items}
        )
    result.update(utilisation_metrics)

    if not shift_df.empty and "production_units" in shift_df.columns:
        productive_rows = shift_df[shift_df["production_units"] > 0]
        days_with_work = set(int(day) for day in productive_rows["day"].tolist())
        shift_keys_with_work = {
            (int(row["day"]), str(row["shift_id"]))
            for _, row in productive_rows[["day", "shift_id"]].iterrows()
        }
    else:
        days_with_work = set()
        shift_keys_with_work = set()

    makespan_metrics = compute_makespan_metrics(
        pb,
        shift_df,
        fallback_days=days_with_work,
        fallback_shift_keys=shift_keys_with_work,
    )
    result.update(makespan_metrics)

    total_hours_recorded = float(shift_df.get("total_hours", pd.Series(dtype=float)).sum())
    avg_production_rate = (
        delivered_total / total_hours_recorded if total_hours_recorded > 0 else 0.0
    )

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

    return KPIResult(
        totals=result,
        shift_calendar=shift_df,
        day_calendar=day_df,
        sequencing_debug=playback_result.sequencing_debug,
    )
