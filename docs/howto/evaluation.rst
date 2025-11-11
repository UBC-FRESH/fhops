Evaluation Workflows
====================

FHOPS exposes deterministic playback tooling so you can inspect shift/day activity, idle
capacity, mobilisation costs, and sequencing signals without leaving the CLI. This guide shows
how to run the new ``fhops eval playback`` command and interpret its outputs.

Running deterministic playback
------------------------------

The playback command requires two inputs:

* ``--scenario`` — path to the scenario YAML.
* ``--assignments`` — CSV with ``machine_id``, ``block_id``, ``day``, and optional ``shift_id`` and
  ``production`` columns. Any schedule exported by ``fhops solve-mip`` or ``fhops solve-heur`` is
  already in the expected format.

Example (building on the regression fixtures):

.. code-block:: console

   $ fhops solve-heur tests/fixtures/regression/regression.yaml --out tmp/regression_sa.csv
   $ fhops eval playback --scenario tests/fixtures/regression/regression.yaml \
       --assignments tmp/regression_sa.csv \
       --shift-out tmp/regression_shift.csv \
       --day-out tmp/regression_day.csv

The command prints two tables:

* **Shift Playback Summary** — one row per machine/day/shift. Columns include production units,
  worked hours, idle hours (when ``--include-idle`` is used), mobilisation cost, and sequencing
  violation counts gathered during playback.
* **Day Playback Summary** — day-level aggregation with production, total/idle hours, mobilisation
  totals, completed block count, and sequencing conflicts.

If you pass ``--shift-out`` or ``--day-out`` the same metrics are written to CSV files. The output
schema matches the in-memory ``ShiftSummary`` and ``DaySummary`` dataclasses.

Optional flags
--------------

``--include-idle`` emits rows for machine/shift combinations that were available but never assigned.
This is useful when you want to inspect under-utilisation alongside productive shifts. Without the
flag, only shifts that perform work are listed.

``--shift-out`` and ``--day-out`` accept CSV paths. Folders are created automatically if they do not
exist.

``--kpi-mode`` toggles between ``basic`` and ``extended`` KPI summaries in the CLI output. The basic
view focuses on production/mobilisation; the extended view includes utilisation, downtime, and weather
metrics derived from the playback summaries.

Reporting templates
-------------------

The repository ships with lightweight templates under ``docs/templates/`` that you can use to stage
KPI snapshots in Markdown/CSV reports. For example ``docs/templates/kpi_summary.md`` is a simple
Markdown table containing placeholders such as ``{{ total_production }}``, ``{{ uptime_ratio_mean_day }}``,
and ``{{ downtime_hours_by_machine }}``.

Populate the template with the output of ``compute_kpis`` (or the CLI telemetry payload) to produce a
shareable summary:

.. code-block:: python

   import pathlib
   from string import Template

   from fhops.evaluation import compute_kpis
   from fhops.scenario.contract import Problem
   from fhops.scenario.io import load_scenario

   template_path = pathlib.Path("docs/templates/kpi_summary.md")
   template = Template(template_path.read_text(encoding="utf-8"))

   pb = Problem.from_scenario(load_scenario("examples/minitoy/scenario.yaml"))
   assignments = pd.read_csv("tests/fixtures/playback/minitoy_assignments.csv")
   kpi_data = compute_kpis(pb, assignments).to_dict()

   report = template.safe_substitute({key: kpi_data.get(key, "-") for key in kpi_data})
   pathlib.Path("tmp/minitoy_kpi_summary.md").write_text(report, encoding="utf-8")

You can embed the generated Markdown as-is in docs/notebooks or adapt the template to match your
reporting format (CSV, HTML, etc.). A CSV variant lives alongside the Markdown template, so you can
generate spreadsheet-friendly snapshots just as easily:

.. code-block:: python

   csv_template = Template(pathlib.Path("docs/templates/kpi_summary.csv").read_text(encoding="utf-8"))
   pathlib.Path("tmp/minitoy_kpi_summary.csv").write_text(
       csv_template.safe_substitute({key: kpi_data.get(key, "-") for key in kpi_data}),
       encoding="utf-8",
   )

Parquet and Markdown exports
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set ``--shift-parquet`` / ``--day-parquet`` to emit Parquet artefacts. These require ``pyarrow`` or
``fastparquet``. The command fails early with a helpful message if neither backend is installed.

Use ``--summary-md`` to generate a Markdown digest containing topline metrics (sample count, total
production, average utilisation) plus a preview table of the first 10 day-level rows. This is handy
for dropping rich summaries into release notes or retrospective documents.

Quickstart example
------------------

.. code-block:: console

   $ fhops eval playback examples/minitoy/scenario.yaml \
       --assignments tests/fixtures/playback/minitoy_assignments.csv \
       --samples 5 \
       --downtime-prob 0.1 \
       --weather-prob 0.2 \
       --landing-prob 0.3 \
       --shift-out tmp/minitoy_shift.csv \
       --day-out tmp/minitoy_day.csv \
       --shift-parquet tmp/minitoy_shift.parquet \
       --day-parquet tmp/minitoy_day.parquet \
       --summary-md tmp/minitoy_summary.md \
       --telemetry-log tmp/minitoy_playback.jsonl

The command prints rich tables to the terminal, writes CSV/Parquet/Markdown artefacts, and captures a
JSONL telemetry record containing the same aggregate metrics written to disk.

Load the Parquet file, compute machine utilisation, and sanity-check totals:

.. code-block:: python

   import pandas as pd
   from fhops.evaluation import machine_utilisation_summary, playback_summary_metrics

   shift_df = pd.read_parquet("tmp/minitoy_shift.parquet")
   day_df = pd.read_parquet("tmp/minitoy_day.parquet")

   utilisation = machine_utilisation_summary(shift_df)
   print(utilisation.filter(["machine_id", "total_hours", "utilisation_ratio"]).head())

   metrics = playback_summary_metrics(shift_df, day_df)
   print(f"Samples captured: {metrics['samples']}")
   print(f"Total production units: {metrics['total_production']:.1f}")

The Markdown summary (``tmp/minitoy_summary.md``) contains topline metrics and preview tables. Open it
in any Markdown viewer or drop it directly into release notes.

Telemetry JSONL records can be ingested by automation scripts or dashboards. Each entry includes the
scenario, sampling configuration, export paths, and summary metrics so playback runs are traceable.

Aggregation helper reference
----------------------------

The helper functions in :mod:`fhops.evaluation.playback.aggregates` expose stable DataFrame schemas
that mirror the CLI exports:

* ``shift_dataframe(result)`` — converts a deterministic :class:`PlaybackResult` into a DataFrame with
  ``sample_id``, availability, idle, mobilisation, and sequencing fields.
* ``day_dataframe(result)`` — day-level aggregation with consistent column ordering.
* ``shift_dataframe_from_ensemble(ensemble)`` / ``day_dataframe_from_ensemble(ensemble)`` — accept a
  stochastic :class:`EnsembleResult` and stitch all samples (including the base result when requested)
  into a single DataFrame while preserving ``sample_id``.
* ``machine_utilisation_summary(shift_df)`` — groups shift-level data by machine/sample and reports
  total/available hours, production, mobilisation, and computed utilisation ratios. This is the
  fastest way to build custom utilisation charts.
* ``export_playback(shift_df, day_df, ...)`` — shared serializer used by the CLI and telemetry code;
  it writes CSV/Parquet/Markdown outputs and returns the same summary metrics recorded in telemetry.
* ``compute_kpis(...)`` returns a :class:`fhops.evaluation.KPIResult`, a mapping that exposes scalar
  KPI totals while optionally attaching the canonical shift/day calendars. Use ``to_dict()`` when you
  need a JSON-serialisable payload or the helper ``with_calendars`` to bundle playback DataFrames.
* ``compute_utilisation_metrics(shift_df, day_df)`` — helper under
  :mod:`fhops.evaluation.metrics.aggregates` that produces mean/weighted utilisation values plus
  per-machine and per-role breakdowns.
* ``compute_makespan_metrics(problem, shift_df)`` — derives the latest productive day/shift (makespan)
  according to the scenario’s shift ordering; accepts fallback day/shift sets for deterministic/stochastic blends.

KPI formulas & required signals
-------------------------------

The current KPI bundle includes:

* ``total_production`` — sum of ``production_units`` over all day summaries.
* ``completed_blocks`` — count of blocks whose remaining work is zero after playback.
* ``mobilisation_cost`` — total mobilisation spend accumulated in playback record metadata.
* ``mobilisation_cost_by_machine`` / ``mobilisation_cost_by_landing`` — JSON mappings that expose
  cumulative mobilisation outlay by machine and landing.
* ``sequencing_violation_*`` (when harvest systems are present) — counts and breakdowns derived from the
  heuristic/MIP sequencing checks captured during playback.
* ``utilisation_ratio_mean_*`` / ``utilisation_ratio_weighted_*`` — average and weighted utilisation taken
  from the shift/day calendars, with optional breakdowns by machine or role.
* ``makespan_day`` / ``makespan_shift`` — latest day/shift containing productive assignments according to
  the scenario’s shift definition order.
* ``downtime_hours_total`` / ``downtime_event_count`` / ``downtime_hours_by_machine`` — aggregate downtime
  exposure derived from stochastic sampling (zero for deterministic runs).
* ``downtime_production_loss_est`` — approximate production loss using average production per hour times downtime hours.
* ``weather_severity_total`` / ``weather_severity_by_machine`` — cumulative weather intensity applied during
  stochastic playback, useful for correlating production drops with weather samples.
* ``weather_hours_est`` / ``weather_production_loss_est`` — estimated hours and production impact attributable to weather, based on aggregate severity and average shift hours.

Upcoming KPI extensions planned for Phase 3 will reuse the same shift/day summaries:

* **Weather/downtime penalties** — additional cost categories driven by stochastic events.
* **Landing/system production breakdowns** — richer summaries for dashboards/notebooks.

Before adding a new KPI ensure the required signal exists in either ``ShiftSummary`` or ``DaySummary``.
If a field is missing, extend the playback dataclasses first so both deterministic and stochastic flows
emit the same schema and downstream KPIs remain reproducible.

These helpers are safe to use in notebooks, KPI pipelines, or automation scripts. The schemas are
covered by regression tests so future changes will not silently break downstream consumers.

Stochastic playback toggles
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The command also exposes stochastic options mirroring the API:

* ``--samples`` — number of stochastic samples to evaluate (defaults to ``1`` for deterministic playback).
* ``--downtime-prob`` / ``--downtime-max`` — probability of downtime events and an optional maximum number of assignments to drop per day.
* ``--weather-prob`` / ``--weather-severity`` / ``--weather-window`` — frequency, severity, and duration of weather-induced production reductions.
* ``--landing-prob`` / ``--landing-mult-min`` / ``--landing-mult-max`` / ``--landing-duration`` — sample landing congestion shocks that scale production by a multiplier for a fixed number of days.

By default these probabilities are ``0.0`` so the command behaves deterministically unless you turn them on.
Each sample’s shift/day summaries are concatenated in the exported CSVs, making it easy to aggregate or
visualise variability across runs.

Relationship to KPI evaluation
------------------------------

``fhops evaluate`` (existing command) still computes aggregate KPIs such as mobilisation cost and
sequencing violations. ``fhops eval playback`` complements it by surfacing the raw shift/day data
used to compute those metrics. In future iterations the playback output will feed notebooks,
stochastic sampling, and new KPI calculators documented here.
