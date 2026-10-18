"""KPI helpers for FHOPS schedules."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
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
from fhops.evaluation.playback.core import PlaybackRecord, shift_hours_resolver
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


@dataclass(slots=True)
class _EventLosses:
    downtime_volume: float = 0.0
    weather_volume: float = 0.0
    weather_hours: float = 0.0


def _event_losses(pb: Problem, records: Iterable[PlaybackRecord]) -> _EventLosses:
    """Sum record-level downtime/weather losses (see :func:`compute_kpis` Notes)."""

    scenario = pb.scenario
    rates = {
        (rate.machine_id, rate.block_id): float(rate.rate) for rate in scenario.production_rates
    }
    hours_for = shift_hours_resolver(scenario)
    losses = _EventLosses()
    for record in records:
        shift_hours, _source = hours_for(record.machine_id, record.shift_id, record.day)
        if record.downtime:
            recorded = record.metadata.get("downtime_production_lost")
            if isinstance(recorded, int | float):
                losses.downtime_volume += float(recorded)
            elif record.downtime_hours and shift_hours and record.block_id is not None:
                fraction = min(float(record.downtime_hours) / float(shift_hours), 1.0)
                losses.downtime_volume += fraction * rates.get(
                    (record.machine_id, record.block_id), 0.0
                )
        severity = float(record.weather_severity or 0.0)
        if severity > 0:
            if shift_hours:
                losses.weather_hours += severity * float(shift_hours)
            recorded = record.metadata.get("weather_production_lost")
            if isinstance(recorded, int | float):
                losses.weather_volume += float(recorded)
            elif severity < 1.0 and record.production_units:
                losses.weather_volume += (
                    float(record.production_units) * severity / (1.0 - severity)
                )
    return losses


def compute_kpis(pb: Problem, assignments: pd.DataFrame) -> KPIResult:
    """Compute production, mobilisation, utilisation, and sequencing KPIs from assignments.

    Parameters
    ----------
    pb : fhops.scenario.contract.Problem
        Problem wrapping the scenario whose blocks define ``work_required`` (m³).
    assignments : pandas.DataFrame
        Solver assignments (``machine_id``, ``block_id``, ``day`` and optional ``shift_id``,
        ``assigned``, ``production``) replayed through deterministic playback. May be empty
        (e.g. a solver run that found no solution); see Notes.

    Returns
    -------
    KPIResult
        Scalar KPI totals. Volume KPIs are in m³, the units of ``Block.work_required``:
        ``total_production`` is the volume delivered by each block's terminal role and
        ``remaining_work_total`` / ``staged_production`` the volume still to deliver.

    Notes
    -----
    ``total_production`` is always the playback ``delivered_total``; ``remaining_work_total``
    is ``sum(Block.work_required) - total_production`` (tracked per block by playback). Both
    respect the scenario as given, so for a rolling-horizon window with carried-forward
    ``work_required`` the total is the reduced volume.

    Empty plans (no rows, or no row with ``assigned > 0``) and partial plans are evaluated
    like any other plan, which gives for an empty plan:

    * ``total_production = 0``, ``remaining_work_total = staged_production =
      sum(Block.work_required)``, ``completed_blocks = 0``;
    * ``makespan_day = 0`` and ``makespan_shift = "N/A"``;
    * ``utilisation_ratio_mean_day`` / ``utilisation_ratio_weighted_day`` are ``0`` (every
      available scenario day is idle) and the shift/machine/role utilisation keys are absent
      (there are no worked machine-shifts);
    * ``sequencing_violation_*`` counts are ``0``, ``sequencing_violation_breakdown`` is
      ``"none"`` and ``sequencing_clean_blocks`` counts every harvest-system block (no block
      has a violation, including blocks the plan never touches);
    * the mobilisation, downtime, and weather keys are absent (they are only emitted when
      non-zero).

    FHOPS ≤ 1.0.0 reported ``total_production = sum(Block.work_required)`` and
    ``remaining_work_total = 0`` for an empty assignment frame (#108).

    Downtime and weather loss KPIs (emitted only for frames carrying stochastic event columns,
    e.g. a sample produced by :func:`~fhops.evaluation.playback.run_stochastic_playback`) are
    record-level sums (FHOPS 1.0.1, #116):

    * ``downtime_production_loss_est`` — Σ over downtime records of the proposed volume (m³)
      the downtime event removed from that record (``_downtime_lost``: the full proposed volume
      for a cancelled shift, ``volume × d / shift_hours`` for a partial loss). Records without
      that column use ``rate(machine, block) × min(downtime_hours / shift_hours, 1)``.
    * ``weather_production_loss_est`` — Σ over weather-hit records of the proposed volume (m³)
      removed by weather (``_weather_lost`` = ``volume × severity``); without that column,
      ``production_units × severity / (1 − severity)``.
    * ``weather_hours_est`` — Σ over weather-hit records of ``severity × shift_hours``.

    ``shift_hours`` follows :func:`~fhops.evaluation.playback.core.shift_hours_resolver`. The
    losses are measured on the proposed production of each machine-shift, before sequencing caps,
    so they include upstream (non-terminal) volume; they are not the change in
    ``total_production``, which also reflects knock-on sequencing effects. FHOPS 1.0.0 estimated
    both as hours × (delivered terminal volume / recorded hours of every role), which does not
    match the volume the events actually removed.
    """

    playback_result = run_playback(pb, assignments, config=PlaybackConfig())
    shift_df = shift_dataframe(playback_result)
    day_df = day_dataframe(playback_result)

    delivered_total = float(playback_result.delivered_total)
    remaining_work_total = float(playback_result.remaining_work_total)

    sc = pb.scenario
    total_required = sum(block.work_required for block in sc.blocks)

    mobilisation_cost = 0.0
    mobilisation_by_machine: dict[str, float] = defaultdict(float)
    mobilisation_by_landing: dict[str, float] = defaultdict(float)
    completed_blocks: set[str] = set()
    seq_violation_events = 0
    seq_violation_blocks: set[str] = set()
    seq_violation_days: set[tuple[str, int]] = set()
    seq_reason_counts: Counter[str] = Counter()

    for record in playback_result.records:
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

    result: dict[str, float | int | str] = {
        "total_production": delivered_total,
        "completed_blocks": float(len(completed_blocks)),
    }
    staged_volume = remaining_work_total
    residual = float(total_required) - delivered_total
    if residual >= 0 and abs(staged_volume - residual) <= 1e-6:
        staged_volume = residual
    if abs(staged_volume) <= 1e-6:
        staged_volume = 0.0
    result["staged_production"] = staged_volume
    result["remaining_work_total"] = staged_volume
    # ``total_required - remaining`` is only a float-tidy form of the delivered volume; never
    # let it replace ``delivered_total`` when the two disagree (FHOPS <= 1.0.0 did, so an empty
    # plan reported the full scenario volume as delivered, #108).
    adjusted_total = float(total_required) - staged_volume
    tolerance = max(1e-6, 1e-9 * float(total_required))
    if adjusted_total >= 0 and abs(adjusted_total - delivered_total) <= tolerance:
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

    loss = _event_losses(pb, playback_result.records)

    if "downtime_hours" in shift_df.columns:
        total_downtime_hours = float(shift_df["downtime_hours"].sum())
        if total_downtime_hours > 0:
            result["downtime_hours_total"] = total_downtime_hours
            result["downtime_production_loss_est"] = loss.downtime_volume
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
            result["weather_hours_est"] = loss.weather_hours
            result["weather_production_loss_est"] = loss.weather_volume
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
