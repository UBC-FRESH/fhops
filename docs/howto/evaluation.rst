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

Relationship to KPI evaluation
------------------------------

``fhops evaluate`` (existing command) still computes aggregate KPIs such as mobilisation cost and
sequencing violations. ``fhops eval playback`` complements it by surfacing the raw shift/day data
used to compute those metrics. In future iterations the playback output will feed notebooks,
stochastic sampling, and new KPI calculators documented here.
