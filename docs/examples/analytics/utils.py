"""Shared utilities for analytics notebooks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import altair as alt
import pandas as pd

from fhops.evaluation import (
    PlaybackConfig,
    SamplingConfig,
    day_dataframe,
    day_dataframe_from_ensemble,
    run_playback,
    run_stochastic_playback,
    shift_dataframe,
    shift_dataframe_from_ensemble,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.scenario.synthetic import sampling_config_for, SyntheticDatasetConfig


@dataclass
class PlaybackTables:
    shift: pd.DataFrame
    day: pd.DataFrame


def load_deterministic_playback(
    scenario_path: Path,
    assignments_path: Path,
    playback_config: PlaybackConfig | None = None,
) -> PlaybackTables:
    """Run deterministic playback and return shift/day tables."""
    scenario = load_scenario(scenario_path)
    problem = Problem.from_scenario(scenario)
    assignments = pd.read_csv(assignments_path)

    playback = run_playback(problem, assignments, config=playback_config)
    shift_df = shift_dataframe(playback)
    day_df = day_dataframe(playback)
    return PlaybackTables(shift=shift_df, day=day_df)


def run_stochastic_summary(
    scenario_path: Path,
    assignments_path: Path,
    sampling_config: SamplingConfig | None = None,
    *,
    tier: str | None = None,
) -> tuple[PlaybackTables, SamplingConfig]:
    """Execute stochastic playback, returning tables and the effective sampling config."""
    scenario = load_scenario(scenario_path)
    problem = Problem.from_scenario(scenario)
    assignments = pd.read_csv(assignments_path)

    if sampling_config is None:
        config = SyntheticDatasetConfig(
            name=scenario.name,
            tier=tier,
            num_blocks=len(scenario.blocks),
            num_days=scenario.num_days,
            num_machines=len(scenario.machines),
        )
        sampling_config = sampling_config_for(config)

    ensemble = run_stochastic_playback(problem, assignments, sampling_config=sampling_config)
    shift_df = shift_dataframe_from_ensemble(ensemble)
    day_df = day_dataframe_from_ensemble(ensemble)
    tables = PlaybackTables(shift=shift_df, day=day_df)
    return tables, sampling_config


def plot_production_by_day(day_df: pd.DataFrame, *, sample_id: int | None = None) -> alt.Chart:
    """Plot production by day (optionally filtered to a specific sample)."""
    data = day_df
    if sample_id is not None and "sample_id" in day_df.columns:
        data = day_df[day_df["sample_id"] == sample_id]
    return (
        alt.Chart(data)
        .mark_bar()
        .encode(
            x="day:O",
            y=alt.Y("production_units:Q", title="Production (units)"),
            color="sample_id:N" if "sample_id" in data.columns else alt.value("#1f77b4"),
        )
        .properties(width=500, height=240)
    )


def plot_utilisation_heatmap(shift_df: pd.DataFrame) -> alt.Chart:
    """Heatmap of utilisation ratios by machine/day."""
    data = shift_df.copy()
    if "sample_id" in data.columns:
        data = data.groupby(["machine_id", "day"], as_index=False)["utilisation_ratio"].mean()

    return (
        alt.Chart(data)
        .mark_rect()
        .encode(
            x=alt.X("day:O", title="Day"),
            y=alt.Y("machine_id:O", title="Machine"),
            color=alt.Color("utilisation_ratio:Q", title="Utilisation", scale=alt.Scale(scheme="blues")),
        )
        .properties(width=500, height=240)
    )


def plot_distribution(
    values: Iterable[float],
    *,
    title: str,
    xlabel: str,
) -> alt.Chart:
    """Simple histogram for sample distributions."""
    series = pd.Series(list(values), name=xlabel)
    return (
        alt.Chart(series.to_frame())
        .mark_bar(opacity=0.75)
        .encode(
            x=alt.X(f"{xlabel}:Q", bin=alt.Bin(maxbins=20), title=xlabel),
            y=alt.Y("count()", title="Frequency"),
        )
        .properties(title=title, width=400, height=240)
    )
