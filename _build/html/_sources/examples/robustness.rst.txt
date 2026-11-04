Stochastic Robustness Walkthrough
=================================

This walkthrough shows how to explore schedule robustness by sampling stochastic events and
summarising the resulting KPI bundle. The workflow mirrors the examples shipped with the repository,
so you can convert it into a Jupyter notebook or run it inline with ``python -m``.

Prerequisites
-------------

* A scenario YAML (we reuse ``examples/med42/scenario.yaml``).
* A baseline assignments CSV (``tests/fixtures/playback/med42_assignments.csv`` is bundled).
* ``pyarrow`` so Parquet exports and playback utilities operate without fallbacks.

Code Walkthrough
----------------

.. code-block:: python

   import json
   from pathlib import Path

   import pandas as pd

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

   scenario_path = Path("examples/med42/scenario.yaml")
   assignments_path = Path("tests/fixtures/playback/med42_assignments.csv")

   problem = Problem.from_scenario(load_scenario(scenario_path))
   assignments = pd.read_csv(assignments_path)

   sampling = SamplingConfig(samples=5, base_seed=42)
   sampling.downtime.enabled = True
   sampling.downtime.probability = 0.6
   sampling.downtime.max_concurrent = 2
   sampling.weather.enabled = True
   sampling.weather.day_probability = 0.4
   sampling.weather.severity_levels = {"default": 0.35}
   sampling.weather.impact_window_days = 2
   sampling.landing.enabled = True
   sampling.landing.probability = 0.5
   sampling.landing.capacity_multiplier_range = (0.4, 0.8)
   sampling.landing.duration_days = 2

   ensemble = run_stochastic_playback(problem, assignments, sampling_config=sampling)
   shift_df = shift_dataframe_from_ensemble(ensemble)
   day_df = day_dataframe_from_ensemble(ensemble)

   util_metrics = compute_utilisation_metrics(shift_df, day_df)
   makespan_metrics = compute_makespan_metrics(
       problem,
       shift_df,
       fallback_days=day_df[day_df["production_units"] > 0]["day"].astype(int).tolist(),
       fallback_shift_keys=[
           (int(row["day"]), str(row["shift_id"]))
           for _, row in shift_df[shift_df["production_units"] > 0].iterrows()
       ],
   )

   kpi_result = compute_kpis(problem, assignments)
   robustness_snapshot = {
       "shift_rows": len(shift_df),
       "day_rows": len(day_df),
       "production_units_sum": float(shift_df["production_units"].sum()),
       "total_hours_sum": float(shift_df["total_hours"].sum()),
       "kpis": kpi_result.to_dict(),
       "utilisation": util_metrics,
       "makespan": makespan_metrics,
   }

   Path("tmp/med42_robustness.json").write_text(
       json.dumps(robustness_snapshot, indent=2, sort_keys=True),
       encoding="utf-8",
   )

Interpretation
--------------

The resulting JSON file captures:

* The size of the stochastic ensemble (rows at shift/day granularity).
* The full KPI bundle (including downtime/weather loss estimates).
* Summary statistics for utilisation and makespan across the sampled runs.

Pair the JSON with the KPI templates under ``docs/templates/`` or use Pandas to convert the
DataFrames to charts/tables. A natural notebook extension would compute percentile bands for key KPIs
and visualise production distributions per landing/system.

Next Steps
----------

* Swap the bundled fixtures for your scenario/assignments.
* Increase ``samples`` or tweak the event configuration to match your robustness study.
* Export Parquet/CSV snapshots from ``shift_dataframe_from_ensemble`` or ``day_dataframe_from_ensemble``
  to drive downstream dashboards.
