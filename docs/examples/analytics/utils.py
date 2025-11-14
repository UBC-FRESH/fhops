"""Shared utilities for analytics notebooks."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

try:  # optional dependency for rich charts
    import altair as alt  # type: ignore
except ModuleNotFoundError:
    alt = None  # type: ignore

try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None

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
from fhops.scenario.synthetic import SyntheticDatasetConfig, sampling_config_for


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

    light_mode = os.getenv("FHOPS_ANALYTICS_LIGHT")
    if light_mode:
        sampling_config = sampling_config.model_copy()
        sampling_config.samples = max(1, min(sampling_config.samples, 4))
        if sampling_config.downtime.enabled:
            sampling_config.downtime.probability = min(sampling_config.downtime.probability, 0.1)
        if sampling_config.weather.enabled:
            sampling_config.weather.day_probability = min(
                sampling_config.weather.day_probability, 0.2
            )
        if sampling_config.landing.enabled:
            sampling_config.landing.probability = min(sampling_config.landing.probability, 0.2)

    ensemble = run_stochastic_playback(problem, assignments, sampling_config=sampling_config)
    shift_df = shift_dataframe_from_ensemble(ensemble)
    day_df = day_dataframe_from_ensemble(ensemble)
    tables = PlaybackTables(shift=shift_df, day=day_df)
    return tables, sampling_config


def _require_backend() -> None:
    if alt is None and plt is None:
        raise RuntimeError("Install 'altair' or 'matplotlib' to render charts.")


def plot_production_by_day(day_df: pd.DataFrame, *, sample_id: int | None = None):
    """Plot production by day (optionally filtered to a specific sample)."""
    data = day_df
    if sample_id is not None and "sample_id" in day_df.columns:
        data = day_df[day_df["sample_id"] == sample_id]
    if alt is not None:
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
    _require_backend()
    assert plt is not None
    fig, ax = plt.subplots(figsize=(6, 3))
    bar_data = data.groupby("day")["production_units"].sum()
    ax.bar(bar_data.index.astype(str), bar_data.values, color="#1f77b4")
    ax.set_xlabel("Day")
    ax.set_ylabel("Production (units)")
    ax.set_title("Production by Day")
    fig.tight_layout()
    return fig


def plot_utilisation_heatmap(shift_df: pd.DataFrame):
    """Heatmap of utilisation ratios by machine/day."""
    data = shift_df.copy()
    if "sample_id" in data.columns:
        data = data.groupby(["machine_id", "day"], as_index=False)["utilisation_ratio"].mean()
    if alt is not None:
        return (
            alt.Chart(data)
            .mark_rect()
            .encode(
                x=alt.X("day:O", title="Day"),
                y=alt.Y("machine_id:O", title="Machine"),
                color=alt.Color(
                    "utilisation_ratio:Q", title="Utilisation", scale=alt.Scale(scheme="blues")
                ),
            )
            .properties(width=500, height=240)
        )
    _require_backend()
    assert plt is not None
    pivot = data.pivot(index="machine_id", columns="day", values="utilisation_ratio").sort_index()
    fig, ax = plt.subplots(figsize=(6, 3))
    im = ax.imshow(pivot, aspect="auto", cmap="Blues", vmin=0, vmax=max(1.0, pivot.max().max()))
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns.astype(str))
    ax.set_xlabel("Day")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_ylabel("Machine")
    ax.set_title("Utilisation Heatmap")
    fig.colorbar(im, ax=ax, label="Utilisation")
    fig.tight_layout()
    return fig


def plot_distribution(
    values: Iterable[float],
    *,
    title: str,
    xlabel: str,
):
    """Simple histogram for sample distributions."""
    series = pd.Series(list(values), name=xlabel)
    if alt is not None:
        return (
            alt.Chart(series.to_frame())
            .mark_bar(opacity=0.75)
            .encode(
                x=alt.X(f"{xlabel}:Q", bin=alt.Bin(maxbins=20), title=xlabel),
                y=alt.Y("count()", title="Frequency"),
            )
            .properties(title=title, width=400, height=240)
        )
    _require_backend()
    assert plt is not None
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.hist(series.values, bins=20, color="#1f77b4", alpha=0.75)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Frequency")
    ax.set_title(title)
    fig.tight_layout()
    return fig
