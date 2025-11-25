from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fhops.evaluation import (
    SamplingConfig,
    compute_kpis,
    compute_makespan_metrics,
    compute_utilisation_metrics,
    day_dataframe_from_ensemble,
    run_stochastic_playback,
    shift_dataframe_from_ensemble,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

FIXTURE_DIR = Path("tests/fixtures/kpi")
DETERMINISTIC_FIXTURE = FIXTURE_DIR / "deterministic.json"
STOCHASTIC_FIXTURE = FIXTURE_DIR / "stochastic.json"


@pytest.mark.parametrize("scenario_name", ["minitoy", "med42"])
@pytest.mark.milp_refactor
def test_kpi_deterministic_snapshot(scenario_name: str) -> None:
    fixture_data = json.loads(DETERMINISTIC_FIXTURE.read_text(encoding="utf-8"))[scenario_name]

    scenario_path = Path(f"examples/{scenario_name}/scenario.yaml")
    assignments_path = Path(f"tests/fixtures/playback/{scenario_name}_assignments.csv")
    pb = Problem.from_scenario(load_scenario(scenario_path))
    assignments = pd.read_csv(assignments_path)

    kpis = {
        key: round(value, 6) if isinstance(value, float) else value
        for key, value in compute_kpis(pb, assignments).to_dict().items()
    }

    assert kpis == fixture_data


@pytest.mark.milp_refactor
def test_kpi_stochastic_snapshot() -> None:
    fixture_data = json.loads(STOCHASTIC_FIXTURE.read_text(encoding="utf-8"))

    scenario_path = Path("examples/med42/scenario.yaml")
    assignments_path = Path("tests/fixtures/playback/med42_assignments.csv")
    pb = Problem.from_scenario(load_scenario(scenario_path))
    assignments = pd.read_csv(assignments_path)

    cfg = SamplingConfig(samples=3, base_seed=42)
    cfg.downtime.enabled = True
    cfg.downtime.probability = 0.6
    cfg.downtime.max_concurrent = 2
    cfg.weather.enabled = True
    cfg.weather.day_probability = 0.4
    cfg.weather.severity_levels = {"default": 0.35}
    cfg.weather.impact_window_days = 2
    cfg.landing.enabled = True
    cfg.landing.probability = 0.5
    cfg.landing.capacity_multiplier_range = (0.4, 0.8)
    cfg.landing.duration_days = 2

    ensemble = run_stochastic_playback(pb, assignments, sampling_config=cfg)

    shift_df = shift_dataframe_from_ensemble(ensemble)
    day_df = day_dataframe_from_ensemble(ensemble)

    util_metrics = compute_utilisation_metrics(shift_df, day_df)
    makespan_metrics = compute_makespan_metrics(
        pb,
        shift_df,
        fallback_days=day_df[day_df["production_units"] > 0]["day"].astype(int).tolist(),
        fallback_shift_keys=[
            (int(row["day"]), str(row["shift_id"]))
            for _, row in shift_df[shift_df["production_units"] > 0].iterrows()
        ],
    )

    snapshot = {
        "shift_rows": int(len(shift_df)),
        "day_rows": int(len(day_df)),
        "production_units_sum": round(float(shift_df["production_units"].sum()), 6),
        "total_hours_sum": round(float(shift_df["total_hours"].sum()), 6),
    }
    snapshot.update(
        {
            key: round(value, 6) if isinstance(value, float) else value
            for key, value in util_metrics.items()
        }
    )
    snapshot.update(
        {
            key: round(value, 6) if isinstance(value, float) else value
            for key, value in makespan_metrics.items()
        }
    )

    total_prod = float(shift_df["production_units"].sum())
    total_hours = float(shift_df["total_hours"].sum())
    avg_rate = total_prod / total_hours if total_hours > 0 else 0.0

    if "downtime_hours" in shift_df.columns:
        downtime_hours_total = float(shift_df["downtime_hours"].sum())
        snapshot["downtime_hours_total"] = round(downtime_hours_total, 6)
        snapshot["downtime_event_count"] = int(shift_df["downtime_events"].sum())
        snapshot["downtime_production_loss_est"] = round(downtime_hours_total * avg_rate, 6)
    if "weather_severity_total" in shift_df.columns:
        weather_total = float(shift_df["weather_severity_total"].sum())
        snapshot["weather_severity_total"] = round(weather_total, 6)
        avg_shift_hours = total_hours / len(shift_df) if len(shift_df) else 0.0
        weather_hours_est = weather_total * avg_shift_hours
        snapshot["weather_hours_est"] = round(weather_hours_est, 6)
        snapshot["weather_production_loss_est"] = round(weather_hours_est * avg_rate, 6)

    assert snapshot == fixture_data
