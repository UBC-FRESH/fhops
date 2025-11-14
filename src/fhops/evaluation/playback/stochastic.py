"""Stochastic playback helpers (downtime, weather sampling)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, TypedDict, cast

import numpy as np
import pandas as pd

from fhops.scenario.contract import Problem

from .adapters import assignments_to_records
from .core import PlaybackResult, run_playback
from .events import SamplingConfig

__all__ = [
    "SamplingContext",
    "PlaybackEvent",
    "DowntimeEvent",
    "WeatherEvent",
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


class DowntimeEvent:
    """Randomly remove assignments to simulate downtime."""

    def __init__(self, config):
        self.config = config

    def apply(
        self,
        context: SamplingContext,
        assignments: pd.DataFrame,
        base_production: dict[Key, float],
    ) -> pd.DataFrame:
        df = assignments.copy()
        if df.empty or self.config.probability <= 0:
            return df
        scenario = context.problem.scenario
        machine_roles = {
            machine.id: getattr(machine, "role", None) for machine in scenario.machines
        }
        df["_target_role"] = df["machine_id"].map(machine_roles)
        role_filter = self.config.target_machine_roles
        mask = df["_target_role"].notna() if role_filter else pd.Series(True, index=df.index)
        if role_filter:
            allowed = set(role_filter)
            mask &= df["_target_role"].isin(allowed)
        candidates = df[mask]
        if candidates.empty:
            df.drop(columns="_target_role", inplace=True)
            return df

        df["_downtime"] = 0
        grouped = candidates.groupby("day")
        for day, day_frame in grouped:
            indices = day_frame.index.tolist()
            rng = context.rng
            if self.config.max_concurrent is not None:
                k = min(len(indices), self.config.max_concurrent)
                if k == 0:
                    continue
                selected = rng.choice(indices, size=k, replace=False)
            else:
                selected = [idx for idx in indices if rng.random() <= self.config.probability]
            for idx in selected:
                row_index = cast(int | str, idx)
                df.loc[row_index, "assigned"] = 0
                df.loc[row_index, "production"] = 0.0
                df.loc[row_index, "_downtime"] = 1
        df.drop(columns="_target_role", inplace=True)
        return df


class WeatherEvent:
    """Adjust production based on weather severity."""

    def __init__(self, config):
        self.config = config

    def apply(
        self,
        context: SamplingContext,
        assignments: pd.DataFrame,
        base_production: dict[Key, float],
    ) -> pd.DataFrame:
        df = assignments.copy()
        if df.empty or self.config.day_probability <= 0:
            return df
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
            return df

        shifts_filter = set(self.config.affected_shifts) if self.config.affected_shifts else None

        df["_weather_severity"] = 0.0
        for idx, row in df.iterrows():
            severity = affected.get(int(row["day"]))
            if severity is None:
                continue
            shift_id = row.get("shift_id", "S1")
            if shifts_filter and shift_id not in shifts_filter:
                continue
            key = (
                str(row["machine_id"]),
                str(row["block_id"]),
                int(row["day"]),
                str(shift_id),
            )
            base = base_production.get(key, row.get("production", 0.0) or 0.0)
            adjusted = max(base * (1 - severity), 0.0)
            row_index = cast(int | str, idx)
            df.loc[row_index, "production"] = adjusted
            df.loc[row_index, "_weather_severity"] = severity
        return df


class LandingShockState(TypedDict):
    duration: int
    multiplier: float
    remaining: int


class LandingShockEvent:
    """Reduce landing throughput via random shocks."""

    def __init__(self, config):
        self.config = config

    def apply(
        self,
        context: SamplingContext,
        assignments: pd.DataFrame,
        base_production: dict[Key, float],
    ) -> pd.DataFrame:
        df = assignments.copy()
        if df.empty or self.config.probability <= 0:
            return df
        rng = context.rng
        scenario = context.problem.scenario

        landings = self.config.target_landing_ids or [landing.id for landing in scenario.landings]
        if not landings:
            return df

        shocks: dict[str, LandingShockState] = {}
        for landing_id in landings:
            if rng.random() <= self.config.probability:
                duration = max(self.config.duration_days, 1)
                lower, upper = self.config.capacity_multiplier_range
                multiplier = float(rng.uniform(lower, upper))
                shocks[landing_id] = {
                    "duration": duration,
                    "multiplier": multiplier,
                    "remaining": duration,
                }

        if not shocks:
            return df

        landing_lookup = {}
        for block in scenario.blocks:
            landing_lookup[block.id] = block.landing_id

        df["_landing_multiplier"] = 1.0
        for idx, row in df.iterrows():
            block_id = str(row["block_id"])
            landing_id = landing_lookup.get(block_id)
            if not landing_id or landing_id not in shocks:
                continue
            shock = shocks[landing_id]
            if shock["remaining"] <= 0:
                continue
            multiplier = shock["multiplier"]
            key = (
                str(row["machine_id"]),
                block_id,
                int(row["day"]),
                str(row.get("shift_id", "S1")),
            )
            baseline = base_production.get(key, row.get("production", 0.0) or 0.0)
            adjusted = max(baseline * multiplier, 0.0)
            row_index = cast(int | str, idx)
            df.loc[row_index, "production"] = adjusted
            df.loc[row_index, "_landing_multiplier"] = multiplier
            shock["remaining"] -= 1

        return df


@dataclass(slots=True)
class PlaybackSample:
    sample_id: int
    result: PlaybackResult


@dataclass(slots=True)
class EnsembleResult:
    base_result: PlaybackResult
    samples: list[PlaybackSample]


def _default_events(config: SamplingConfig) -> list[PlaybackEvent]:
    events: list[PlaybackEvent] = []
    if config.downtime.enabled:
        events.append(DowntimeEvent(config.downtime))
    if config.weather.enabled:
        events.append(WeatherEvent(config.weather))
    if config.landing.enabled:
        events.append(LandingShockEvent(config.landing))
    return events


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "shift_id" not in result.columns:
        result["shift_id"] = "S1"
    if "assigned" not in result.columns:
        result["assigned"] = 1
    return result


def _build_production_map(problem: Problem, assignments: pd.DataFrame) -> dict[Key, float]:
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
    """Run stochastic playback over multiple samples."""

    base_assignments = _ensure_columns(assignments)
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
