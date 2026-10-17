"""Stochastic playback helpers (downtime, weather, landing shocks).

This module replays a fixed schedule under sampled operational disturbances to quantify
schedule robustness. Each sample copies the deterministic assignments, applies the configured
events in order (downtime → weather → landing shocks), and re-runs deterministic playback so
the sequencing tracker re-caps production. Event effects compose multiplicatively on the
assignment's production (volume, m³). Sample ``i`` uses ``numpy.random.default_rng(base_seed +
i)`` shared by all events in that order, so results are reproducible for a given seed and event
configuration.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, cast

import numpy as np
import pandas as pd

from fhops.scenario.contract import Problem

from .adapters import (
    DEFAULT_SHIFT_ID,
    assignments_to_records,
    normalise_shift_ids,
    shift_hours_resolver,
)
from .core import PlaybackResult, run_playback
from .events import SamplingConfig

__all__ = [
    "SamplingContext",
    "PlaybackEvent",
    "DowntimeEvent",
    "WeatherEvent",
    "LandingShockEvent",
    "PlaybackSample",
    "EnsembleResult",
    "run_stochastic_playback",
]


Key = tuple[str, str, int, str]


@dataclass(slots=True)
class SamplingContext:
    """Per-sample execution context."""

    problem: Problem
    sample_id: int
    rng: np.random.Generator
    config: SamplingConfig


class PlaybackEvent(Protocol):
    """Stochastic event modifying assignments before playback summarisation."""

    def apply(
        self,
        context: SamplingContext,
        assignments: pd.DataFrame,
        base_production: dict[Key, float],
    ) -> pd.DataFrame: ...


def _row_key(row: pd.Series) -> Key:
    """Return the ``(machine, block, day, shift)`` production-map key for an assignment row."""
    return (
        str(row["machine_id"]),
        str(row["block_id"]),
        int(row["day"]),
        str(row.get("shift_id", DEFAULT_SHIFT_ID)),
    )


def _current_production(row: pd.Series, base_production: dict[Key, float]) -> float:
    """Return the row's current production, falling back to the deterministic baseline."""
    value = row.get("production")
    if value is not None and pd.notna(value):
        return float(value)
    return float(base_production.get(_row_key(row), 0.0) or 0.0)


def _restore_index(df: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    """Give ``df`` (a positionally indexed working copy of ``original``) the original index.

    Events work on a ``reset_index(drop=True)`` copy so row updates are positional and duplicate
    index labels in the caller's frame cannot hit several rows at once.
    """
    df.index = original.index
    return df


def _active_mask(df: pd.DataFrame) -> pd.Series:
    """Return a mask of rows that are still assigned (``assigned > 0`` or no flag column)."""
    if "assigned" not in df.columns:
        return pd.Series(True, index=df.index)
    return df["assigned"].fillna(0) > 0


class DowntimeEvent:
    """Remove part or all of a machine-shift's production to simulate downtime.

    Parameters
    ----------
    config : DowntimeEventConfig
        Probability, duration distribution (hours), ``max_concurrent`` and role filter.

    Notes
    -----
    Eligible rows are assignments with ``assigned > 0`` whose machine role passes
    ``target_machine_roles``. Sampling order (deterministic for a given RNG state):

    1. Days are visited in ascending order.
    2. Selection on each day: with ``max_concurrent`` set, ``rng.choice`` draws
       ``min(max_concurrent, n)`` of the day's ``n`` eligible rows without replacement
       (``probability`` only acts as an on/off switch); otherwise one ``rng.random()`` per
       eligible row (in frame order) selects the row when ``<= probability``.
    3. For each selected row (in selection order) one ``rng.normal(mean_duration_hours,
       std_duration_hours)`` draw gives the duration ``d``, clipped to ``[0, shift_hours]``.

    ``shift_hours`` follows deterministic playback
    (:func:`~fhops.evaluation.playback.core.shift_hours_resolver`): the matching
    ``timeline.shifts`` definition, else the machine's ``daily_hours`` divided by its number of
    shifts that day. With ``0 < d < shift_hours`` the row's production is multiplied by
    ``1 - d / shift_hours``; with ``d == shift_hours`` (or unknown shift hours) the shift is lost
    entirely (``assigned = 0``, ``production = 0``); ``d == 0`` leaves the row untouched.
    Affected rows get ``_downtime = 1``, ``_downtime_hours = d`` and ``_downtime_lost`` (the
    proposed volume removed, m³) so playback summaries report the sampled downtime hours and
    :func:`~fhops.evaluation.metrics.kpis.compute_kpis` the lost volume.

    Row updates are positional: the caller's index (which may contain duplicate labels) is
    ignored and restored on the returned copy.
    """

    def __init__(self, config):
        self.config = config

    def apply(
        self,
        context: SamplingContext,
        assignments: pd.DataFrame,
        base_production: dict[Key, float],
    ) -> pd.DataFrame:
        """Return a copy of ``assignments`` with downtime applied (see class notes)."""
        df = assignments.reset_index(drop=True)
        if df.empty or self.config.probability <= 0:
            return _restore_index(df, assignments)
        scenario = context.problem.scenario
        machine_roles = {
            machine.id: getattr(machine, "role", None) for machine in scenario.machines
        }
        df["_target_role"] = df["machine_id"].map(machine_roles)
        role_filter = self.config.target_machine_roles
        mask = _active_mask(df)
        if role_filter:
            mask &= df["_target_role"].notna() & df["_target_role"].isin(set(role_filter))
        candidates = df[mask]
        df.drop(columns="_target_role", inplace=True)
        if candidates.empty:
            return _restore_index(df, assignments)

        hours_for = shift_hours_resolver(scenario)
        mean = float(self.config.mean_duration_hours)
        std = float(self.config.std_duration_hours)
        if "assigned" not in df.columns:
            df["assigned"] = 1
        if "_downtime" not in df.columns:
            df["_downtime"] = 0
        if "_downtime_hours" not in df.columns:
            df["_downtime_hours"] = 0.0
        if "_downtime_lost" not in df.columns:
            df["_downtime_lost"] = 0.0
        rng = context.rng
        for _day, day_frame in candidates.groupby("day"):
            indices = day_frame.index.tolist()
            if self.config.max_concurrent is not None:
                k = min(len(indices), self.config.max_concurrent)
                if k == 0:
                    continue
                selected = list(rng.choice(indices, size=k, replace=False))
            else:
                selected = [idx for idx in indices if rng.random() <= self.config.probability]
            for idx in selected:
                row_index = cast(int, idx)
                row = cast(pd.Series, df.loc[row_index])
                sampled = float(rng.normal(mean, std))
                shift_hours, _source = hours_for(
                    str(row["machine_id"]),
                    str(row.get("shift_id", DEFAULT_SHIFT_ID)),
                    int(row["day"]),
                )
                duration = max(sampled, 0.0)
                if shift_hours is not None and shift_hours > 0:
                    duration = min(duration, float(shift_hours))
                if duration <= 0.0:
                    continue
                current = _current_production(row, base_production)
                if shift_hours is None or shift_hours <= 0 or duration >= shift_hours:
                    df.loc[row_index, "assigned"] = 0
                    df.loc[row_index, "production"] = 0.0
                    lost = current
                else:
                    remaining = current * (1.0 - duration / shift_hours)
                    df.loc[row_index, "production"] = remaining
                    lost = current - remaining
                df.loc[row_index, "_downtime"] = 1
                df.loc[row_index, "_downtime_hours"] = duration
                df.loc[row_index, "_downtime_lost"] = max(lost, 0.0)
        return _restore_index(df, assignments)


class WeatherEvent:
    """Scale production on days hit by sampled weather spells.

    Parameters
    ----------
    config : WeatherEventConfig
        Day probability, severity levels, spell length and optional shift filter.

    Notes
    -----
    Sampling order: for each distinct assignment day in ascending order, one
    ``rng.random()`` draw starts a spell when ``<= day_probability``; a started spell draws its
    severity level with ``rng.integers``. Each spell covers ``impact_window_days`` consecutive
    days; overlapping spells keep the maximum severity. Affected, still-assigned rows have their
    *current* production multiplied by ``1 - severity`` (so effects compose with earlier
    events) and record ``_weather_severity`` and ``_weather_lost`` (the proposed volume removed,
    m³). ``correlated_days`` is deprecated and ignored. Row updates are positional (the caller's
    index is ignored and restored on the returned copy).
    """

    def __init__(self, config):
        self.config = config

    def apply(
        self,
        context: SamplingContext,
        assignments: pd.DataFrame,
        base_production: dict[Key, float],
    ) -> pd.DataFrame:
        """Return a copy of ``assignments`` with weather impacts applied (see class notes)."""
        df = assignments.reset_index(drop=True)
        if df.empty or self.config.day_probability <= 0:
            return _restore_index(df, assignments)
        rng = context.rng
        severity_levels = self.config.severity_levels or {"moderate": 0.3}
        level_items = list(severity_levels.items())

        affected: dict[int, float] = {}
        days = sorted(df["day"].unique())
        for day in days:
            if rng.random() <= self.config.day_probability:
                label, severity = level_items[rng.integers(0, len(level_items))]
                for offset in range(self.config.impact_window_days):
                    affected_day = day + offset
                    affected[affected_day] = max(affected.get(affected_day, 0.0), severity)

        if not affected:
            return _restore_index(df, assignments)

        shifts_filter = set(self.config.affected_shifts) if self.config.affected_shifts else None
        active = _active_mask(df)

        df["_weather_severity"] = 0.0
        if "_weather_lost" not in df.columns:
            df["_weather_lost"] = 0.0
        for idx, row in df[active].iterrows():
            severity = affected.get(int(row["day"]))
            if severity is None:
                continue
            shift_id = row.get("shift_id", DEFAULT_SHIFT_ID)
            if shifts_filter and shift_id not in shifts_filter:
                continue
            current = _current_production(row, base_production)
            adjusted = max(current * (1 - severity), 0.0)
            row_index = cast(int, idx)
            df.loc[row_index, "production"] = adjusted
            df.loc[row_index, "_weather_severity"] = severity
            df.loc[row_index, "_weather_lost"] = max(current - adjusted, 0.0)
        return _restore_index(df, assignments)


class LandingShockEvent:
    """Reduce landing throughput via random multi-day shocks.

    Parameters
    ----------
    config : LandingShockConfig
        Start probability, multiplier range, duration (days) and optional landing filter.

    Notes
    -----
    Sampling order (deterministic for a given RNG state): landings are visited in the order
    of ``target_landing_ids`` (or ``scenario.landings``); for each landing, every calendar day
    ``1..num_days`` of the scenario horizon is visited in ascending order and one
    ``rng.random()`` draw starts a shock when ``<= probability``. A started shock immediately
    draws its multiplier with ``rng.uniform(low, high)`` and covers ``duration_days``
    consecutive days starting on its start day. When shocks overlap, the minimum multiplier
    applies on each day.

    Every still-assigned row whose block is served by a shocked landing on an affected day has
    its *current* production multiplied by the shock multiplier (so effects compose with earlier
    events) and records ``_landing_multiplier``. Row updates are positional (the caller's index is
    ignored and restored on the returned copy).

    The expected fraction of landing-days under a shock is
    ``1 - (1 - probability) ** duration_days`` (ignoring the horizon start, where fewer start
    days can cover a day); see :class:`~fhops.evaluation.playback.events.LandingShockConfig`.
    """

    def __init__(self, config):
        self.config = config

    def sample_multipliers(self, context: SamplingContext) -> dict[tuple[str, int], float]:
        """Sample landing shocks and return the per-(landing, day) multiplier map.

        Parameters
        ----------
        context : SamplingContext
            Sample context providing the scenario and RNG (consumed in the documented order).

        Returns
        -------
        dict[tuple[str, int], float]
            Mapping ``(landing_id, day) -> multiplier`` for every day covered by at least one
            shock (minimum multiplier across overlapping shocks). Days without a shock are absent.
        """
        rng = context.rng
        scenario = context.problem.scenario
        landings = self.config.target_landing_ids or [landing.id for landing in scenario.landings]
        duration = max(int(self.config.duration_days), 1)
        lower, upper = self.config.capacity_multiplier_range
        multipliers: dict[tuple[str, int], float] = {}
        for landing_id in landings:
            for start_day in range(1, int(scenario.num_days) + 1):
                if rng.random() > self.config.probability:
                    continue
                multiplier = float(rng.uniform(lower, upper))
                for day in range(start_day, start_day + duration):
                    key = (landing_id, day)
                    multipliers[key] = min(multipliers.get(key, multiplier), multiplier)
        return multipliers

    def apply(
        self,
        context: SamplingContext,
        assignments: pd.DataFrame,
        base_production: dict[Key, float],
    ) -> pd.DataFrame:
        """Return a copy of ``assignments`` with landing shocks applied (see class notes)."""
        df = assignments.reset_index(drop=True)
        if df.empty or self.config.probability <= 0:
            return _restore_index(df, assignments)
        scenario = context.problem.scenario
        multipliers = self.sample_multipliers(context)
        if not multipliers:
            return _restore_index(df, assignments)

        landing_lookup = {block.id: block.landing_id for block in scenario.blocks}
        active = _active_mask(df)

        df["_landing_multiplier"] = 1.0
        for idx, row in df[active].iterrows():
            landing_id = landing_lookup.get(str(row["block_id"]))
            if landing_id is None:
                continue
            multiplier = multipliers.get((landing_id, int(row["day"])))
            if multiplier is None:
                continue
            current = _current_production(row, base_production)
            row_index = cast(int, idx)
            df.loc[row_index, "production"] = max(current * multiplier, 0.0)
            df.loc[row_index, "_landing_multiplier"] = multiplier

        return _restore_index(df, assignments)


@dataclass(slots=True)
class PlaybackSample:
    """Container pairing a stochastic sample ID with its :class:`PlaybackResult`."""

    sample_id: int
    result: PlaybackResult


@dataclass(slots=True)
class EnsembleResult:
    """Aggregate of the baseline deterministic playback plus stochastic samples."""

    base_result: PlaybackResult
    samples: list[PlaybackSample]


def _default_events(config: SamplingConfig) -> list[PlaybackEvent]:
    """Instantiate playback events based on the SamplingConfig toggles."""
    events: list[PlaybackEvent] = []
    if config.downtime.enabled:
        events.append(DowntimeEvent(config.downtime))
    if config.weather.enabled:
        events.append(WeatherEvent(config.weather))
    if config.landing.enabled:
        events.append(LandingShockEvent(config.landing))
    return events


def _ensure_columns(problem: Problem, df: pd.DataFrame) -> pd.DataFrame:
    """Return a positionally indexed copy with ``shift_id`` and ``assigned`` columns.

    ``shift_id`` follows :func:`~fhops.evaluation.playback.adapters.normalise_shift_ids`
    (``"S1"`` default for single-shift scenarios, ``ValueError`` for multi-shift scenarios). The
    caller's index is dropped so duplicate labels cannot affect event updates.
    """
    result = normalise_shift_ids(problem, df.reset_index(drop=True))
    if "assigned" not in result.columns:
        result["assigned"] = 1
    return result


def _build_production_map(problem: Problem, assignments: pd.DataFrame) -> dict[Key, float]:
    """Index baseline production by (machine, block, day, shift) for reuse by events."""
    records = assignments_to_records(problem, assignments)
    production_map: dict[Key, float] = {}
    for record in records:
        key = (record.machine_id, record.block_id or "", record.day, record.shift_id)
        production_map[key] = record.production_units or 0.0
    return production_map


def run_stochastic_playback(
    problem: Problem,
    assignments: pd.DataFrame,
    *,
    sampling_config: SamplingConfig,
    events: Iterable[PlaybackEvent] | None = None,
) -> EnsembleResult:
    """Run stochastic playback over multiple samples.

    Parameters
    ----------
    problem : fhops.scenario.contract.Problem
        Problem wrapping the scenario being replayed.
    assignments : pandas.DataFrame
        Deterministic assignments (``machine_id``, ``block_id``, ``day``, optional ``shift_id``,
        ``assigned``, ``production``).
    sampling_config : SamplingConfig
        Number of samples, ``base_seed`` and per-event configuration.
    events : Iterable[PlaybackEvent] | None, default=None
        Custom events applied in the given order; ``None`` builds the enabled default events in
        the order downtime → weather → landing shocks.

    Returns
    -------
    EnsembleResult
        ``base_result`` (deterministic playback of ``assignments``) and one
        :class:`PlaybackSample` per sample.

    Notes
    -----
    Sample ``i`` seeds ``numpy.random.default_rng(sampling_config.base_seed + i)``; every event
    consumes that generator in turn, following the sampling order documented on
    :class:`DowntimeEvent`, :class:`WeatherEvent` and :class:`LandingShockEvent`. Each sample
    starts from the deterministic baseline production and events compose multiplicatively.
    """

    base_assignments = _ensure_columns(problem, assignments)
    base_result = run_playback(problem, base_assignments)

    base_production = _build_production_map(problem, base_assignments)
    production_values = [
        base_production.get(
            (
                row["machine_id"],
                row["block_id"] if pd.notna(row["block_id"]) else "",
                int(row["day"]),
                row["shift_id"],
            ),
            0.0,
        )
        for _, row in base_assignments.iterrows()
    ]
    base_production_series = pd.Series(production_values, index=base_assignments.index)
    num_samples = sampling_config.samples
    active_events = list(events) if events is not None else _default_events(sampling_config)

    samples: list[PlaybackSample] = []
    for sample_id in range(num_samples):
        rng = np.random.default_rng(sampling_config.base_seed + sample_id)
        context = SamplingContext(
            problem=problem, sample_id=sample_id, rng=rng, config=sampling_config
        )

        sample_assignments = base_assignments.copy()
        sample_assignments["production"] = base_production_series.copy()

        for event in active_events:
            sample_assignments = event.apply(context, sample_assignments, base_production)

        playback_result = run_playback(problem, sample_assignments, sample_id=sample_id)
        samples.append(PlaybackSample(sample_id=sample_id, result=playback_result))

    return EnsembleResult(base_result=base_result, samples=samples)
