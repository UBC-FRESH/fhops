Evaluation Workflows
====================

FHOPS exposes deterministic playback tooling so you can inspect shift/day activity, idle
capacity, mobilisation costs, and sequencing signals without leaving the CLI. This guide shows
how to run the ``fhops eval-playback`` command and interpret its outputs.

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
   $ fhops eval-playback tests/fixtures/regression/regression.yaml \
       --assignments tmp/regression_sa.csv \
       --shift-out tmp/regression_shift.csv \
       --day-out tmp/regression_day.csv

The command prints two tables:

* **Shift Playback Summary** — one row per machine/day/shift. Columns include production (m³),
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

   pb = Problem.from_scenario(load_scenario("examples/tiny7/scenario.yaml"))
   assignments = pd.read_csv("tests/fixtures/playback/tiny7_assignments.csv")
   kpi_data = compute_kpis(pb, assignments).to_dict()

   report = template.safe_substitute({key: kpi_data.get(key, "-") for key in kpi_data})
   pathlib.Path("tmp/tiny7_kpi_summary.md").write_text(report, encoding="utf-8")

You can embed the generated Markdown as-is in docs/notebooks or adapt the template to match your
reporting format (CSV, HTML, etc.). A CSV variant lives alongside the Markdown template, so you can
generate spreadsheet-friendly snapshots just as easily:

.. code-block:: python

   csv_template = Template(pathlib.Path("docs/templates/kpi_summary.csv").read_text(encoding="utf-8"))
   pathlib.Path("tmp/tiny7_kpi_summary.csv").write_text(
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

   $ fhops eval-playback examples/tiny7/scenario.yaml \
       --assignments tests/fixtures/playback/tiny7_assignments.csv \
       --samples 5 \
       --downtime-prob 0.1 \
       --weather-prob 0.2 \
       --landing-prob 0.3 \
       --shift-out tmp/tiny7_shift.csv \
       --day-out tmp/tiny7_day.csv \
       --shift-parquet tmp/tiny7_shift.parquet \
       --day-parquet tmp/tiny7_day.parquet \
       --summary-md tmp/tiny7_summary.md \
       --telemetry-log tmp/tiny7_playback.jsonl

The command prints rich tables to the terminal, writes CSV/Parquet/Markdown artefacts, and captures a
JSONL telemetry record containing the same aggregate metrics written to disk.

Load the Parquet file, compute machine utilisation, and sanity-check totals:

.. code-block:: python

   import pandas as pd
   from fhops.evaluation import machine_utilisation_summary, playback_summary_metrics

   shift_df = pd.read_parquet("tmp/tiny7_shift.parquet")
   day_df = pd.read_parquet("tmp/tiny7_day.parquet")

   utilisation = machine_utilisation_summary(shift_df)
   print(utilisation.filter(["machine_id", "total_hours", "utilisation_ratio"]).head())

   metrics = playback_summary_metrics(shift_df, day_df)
   print(f"Samples captured: {metrics['samples']}")
   print(f"Total production units: {metrics['total_production']:.1f}")

The Markdown summary (``tmp/tiny7_summary.md``) contains topline metrics and preview tables. Open it
in any Markdown viewer or drop it directly into release notes.

When you need a quick textual snapshot without leaving the CLI, pass ``--kpi-mode`` to the solver
commands:

.. code-block:: console

   $ fhops solve-heur examples/tiny7/scenario.yaml --out tmp/tiny7_sa.csv --kpi-mode basic

The basic mode prints only production/mobilisation KPIs. Switch to ``--kpi-mode extended`` to include
utilisation, downtime, and weather metrics in the CLI output.

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

* ``total_production`` — delivered volume (m³): the part of ``Block.work_required`` delivered by each
  block's terminal role during playback. ``production_units`` in the shift/day summaries is in the same
  units (m³, like ``ProductionRate.rate``) but counts every role's output.
* ``completed_blocks`` — count of blocks whose remaining volume (``work_required`` minus delivered m³)
  is zero after playback.
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
  exposure derived from the sampled downtime durations (zero for deterministic runs).
* ``downtime_production_loss_est`` — volume (m³) removed by downtime, summed per record from the volume
  the downtime event took out of each hit machine-shift (see below).
* ``weather_severity_total`` / ``weather_severity_by_machine`` — cumulative weather intensity applied during
  stochastic playback, useful for correlating production drops with weather samples.
* ``weather_hours_est`` / ``weather_production_loss_est`` — hours (``severity × shift hours``) and volume (m³)
  removed by weather, summed per record (see below).

Empty and partial plans
~~~~~~~~~~~~~~~~~~~~~~~

An empty assignment table (no rows, or only ``assigned = 0`` rows — e.g. a MILP run that found no
solution) is evaluated like any other plan, so it never looks complete:

* ``total_production = 0``; ``remaining_work_total`` and ``staged_production`` equal
  ``sum(Block.work_required)`` of the evaluated scenario (the carried-forward volume for a rolling
  window); ``completed_blocks = 0``; ``makespan_day = 0`` and ``makespan_shift = "N/A"``.
* Day-level utilisation is ``0`` (every available day is idle); the shift, machine, and role
  utilisation keys are absent, as are the mobilisation, downtime, and weather keys.
* Sequencing counts are ``0`` and ``sequencing_clean_blocks`` counts every harvest-system block.

For any plan (empty, partial, or complete) ``total_production`` is the playback delivered volume
and ``total_production + remaining_work_total = sum(Block.work_required)``. Deterministic and
stochastic playback (:func:`fhops.evaluation.run_playback`,
:func:`fhops.evaluation.run_stochastic_playback`) report ``delivered_total = 0`` and
``remaining_work_total = sum(Block.work_required)`` for an empty plan. FHOPS 1.0.0 reported the
full scenario volume as delivered for an empty frame (`#108
<https://github.com/UBC-FRESH/fhops/issues/108>`_). For rolling-horizon comparisons see
:ref:`rolling-empty-plans`.

Weather & downtime cost assumptions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The loss KPIs are emitted when :func:`~fhops.evaluation.compute_kpis` evaluates an assignment frame that
carries stochastic event columns (for example a sample frame built by
:func:`~fhops.evaluation.run_stochastic_playback`). Since 1.0.1 (`#116
<https://github.com/UBC-FRESH/fhops/issues/116>`_) they are record-level sums:

* ``downtime_hours_total`` sums the sampled downtime hours of every hit machine-shift (cancelled shifts
  count their full shift hours).
* ``downtime_production_loss_est`` sums, over hit machine-shifts, the proposed volume the downtime event
  removed: the whole proposed volume for a cancelled shift, ``volume × d / shift_hours`` for a partial loss
  (the event records it in the private ``_downtime_lost`` column). Frames without that column fall back to
  ``rate(machine, block) × min(downtime_hours / shift_hours, 1)``.
* ``weather_production_loss_est`` sums the proposed volume removed by weather (``volume × severity``,
  column ``_weather_lost``; fallback ``production × severity / (1 − severity)``), and ``weather_hours_est``
  sums ``severity × shift_hours`` over weather-hit machine-shifts.

The losses are measured on each machine-shift's proposed production before sequencing caps, so they
include upstream (non-terminal) volume and do not equal the drop in ``total_production`` (which also
includes knock-on sequencing effects and the other events). FHOPS 1.0.0 estimated both losses as hours ×
(delivered volume ÷ recorded hours of every role), which did not match the volume the events removed.

Shift hours (recorded ``hours_worked``, shift availability used for utilisation, and the downtime
fraction ``d / shift_hours``) come from the matching ``timeline.shifts`` definition; without one, the
machine's ``daily_hours`` is divided by the number of shifts the machine has that day in the shift
calendar (e.g. three shifts → 8 h each for a 24 h machine). Single-shift scenarios use ``daily_hours``
unchanged. FHOPS 1.0.0 recorded the full ``daily_hours`` for every shift of a multi-shift day.

Assignments must carry ``shift_id`` on scenarios with more than one shift per day; playback, KPIs, and
``fhops eval-playback`` raise an error instead of replaying every row as ``S1``. Single-shift scenarios
keep the ``S1`` default.

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
* ``--downtime-prob`` / ``--downtime-max`` / ``--downtime-mean`` / ``--downtime-std`` — probability that a
  machine-shift is hit by downtime (or an exact number of hits per day with ``--downtime-max``) and the
  Normal duration distribution in hours (defaults ``4.0`` / ``1.5``).
* ``--weather-prob`` / ``--weather-severity`` / ``--weather-window`` — frequency, severity, and duration of weather-induced production reductions.
* ``--landing-prob`` / ``--landing-mult-min`` / ``--landing-mult-max`` / ``--landing-duration`` — daily
  probability that a congestion shock starts at each landing, the multiplier range, and the shock length
  in days.

By default these probabilities are ``0.0`` so the command behaves deterministically unless you turn them on.
Each sample’s shift/day summaries are concatenated in the exported CSVs, making it easy to aggregate or
visualise variability across runs.

Stochastic event semantics
~~~~~~~~~~~~~~~~~~~~~~~~~~

:func:`fhops.evaluation.run_stochastic_playback` copies the deterministic assignments for every sample,
applies the enabled events in the order downtime → weather → landing shocks, and re-runs deterministic
playback so sequencing caps still apply. Event effects compose multiplicatively on each assignment's
production (m³). Sample ``i`` uses ``numpy.random.default_rng(base_seed + i)``, shared by the events in that
order, so a given seed and configuration always reproduce the same ensemble.

* **Downtime** (:class:`~fhops.evaluation.playback.events.DowntimeEventConfig`). Days are visited in
  ascending order. On each day every eligible assignment (``assigned > 0``, optional
  ``target_machine_roles``) is hit with ``probability``; with ``max_concurrent`` set, exactly
  ``min(max_concurrent, n)`` of the day's ``n`` eligible assignments are hit instead. Each hit samples a
  duration ``d ~ Normal(mean_duration_hours, std_duration_hours)`` clipped to ``[0, shift_hours]`` and
  multiplies the assignment's production by ``1 - d / shift_hours``. A full-shift loss
  (``d == shift_hours``) cancels the assignment (``assigned = 0``, production ``0``). ``shift_hours`` is the
  matching ``timeline.shifts`` definition, otherwise the machine's ``daily_hours`` divided by its number of
  shifts that day — the same hours deterministic playback records. The shift summaries report ``downtime_hours`` (the sampled hours,
  including cancelled shifts) and ``total_hours = shift_hours - d`` for affected shifts, so
  ``downtime_hours_total`` and utilisation reflect the sampled durations.
* **Weather** (:class:`~fhops.evaluation.playback.events.WeatherEventConfig`). For each assignment day a
  spell starts with ``day_probability``, picks a severity level, and covers ``impact_window_days``
  consecutive days (overlaps keep the highest severity). Affected production is multiplied by
  ``1 - severity``. ``correlated_days`` is deprecated since 1.0.1: it never had an effect, and explicitly
  setting it to a non-default value (``False``) emits a ``DeprecationWarning`` (the default ``True``, e.g. in
  older synthetic ``metadata.yaml`` files, does not warn). Use ``impact_window_days`` to model multi-day
  spells.
* **Landing shocks** (:class:`~fhops.evaluation.playback.events.LandingShockConfig`). For each landing and
  each calendar day of the horizon a shock starts with ``probability``, draws a multiplier uniformly from
  ``capacity_multiplier_range``, and lasts ``duration_days`` calendar days from its start day. Every
  assignment on a block served by that landing has its production scaled by the multiplier on the
  affected days; overlapping shocks use the minimum multiplier. The expected fraction of landing-days
  under a shock is

  .. math::

     f = 1 - (1 - p)^{D}

  with ``p = probability`` and ``D = duration_days`` (days ``d < D`` at the start of the horizon use
  ``d`` instead of ``D``). The default :class:`~fhops.evaluation.playback.events.SamplingConfig`
  (``p = 0.1``, ``D = 1``, multipliers uniform on 0.4–0.8) shocks 10 % of landing-days with a mean
  multiplier of 0.6, i.e. an expected landing throughput loss of about 4 % over the horizon. The synthetic
  tier presets (:data:`fhops.scenario.synthetic.SAMPLING_PRESETS`) were recalibrated for these semantics in
  1.0.1: ``medium`` uses ``p = 0.025``, ``D = 2`` (``f ≈ 4.9 %``) and ``large`` uses ``p = 0.035``,
  ``D = 3`` (``f ≈ 10.1 %``); the 1.0.0 values (``0.18``/``0.25``) would shock 32.8 % / 57.8 % of
  landing-days. ``metadata.yaml`` files of the shipped ``examples/synthetic`` bundles record the presets
  in force when they were generated.
* **Event seeds.** ``seed_offset`` (on every event config) is deprecated since 1.0.1 and ignored — it was
  never used. All events of sample ``i`` draw from ``default_rng(base_seed + i)`` in the order above;
  setting a non-zero ``seed_offset`` emits a ``DeprecationWarning``.

.. note::

   FHOPS 1.0.0 applied landing shocks to the first assignment rows of a shocked landing rather than to
   calendar days, always removed a whole shift on downtime (ignoring the duration settings), and dropped
   downtime-cancelled shifts from the summaries (so ``downtime_hours_total`` stayed at zero). Stochastic
   playback results from 1.0.1 onwards therefore differ from 1.0.0 for the same seed.

Relationship to KPI evaluation
------------------------------

``fhops evaluate`` (existing command) still computes aggregate KPIs such as mobilisation cost and
sequencing violations. ``fhops eval-playback`` complements it by surfacing the raw shift/day data
used to compute those metrics. In future iterations the playback output will feed notebooks,
stochastic sampling, and new KPI calculators documented here.
