Benchmarking Harness
====================

FHOPS ships sample scenarios in ``examples/`` (``minitoy``, ``med42``, ``large84``) that cover
increasing planning horizons. The Phase 2 benchmarking harness runs the MIP and heuristic
solvers across these datasets, captures objectives/KPIs, and stores results for inspection.

Quick Start
-----------

.. code-block:: bash

   fhops bench suite --out-dir tmp/benchmarks
   fhops bench suite --scenario examples/minitoy/scenario.yaml --scenario examples/med42/scenario.yaml --out-dir tmp/benchmarks_med
   fhops bench suite --scenario examples/large84/scenario.yaml --out-dir tmp/benchmarks_large --time-limit 180 --include-sa False

This command:

* loads each bundled scenario (minitoy → med42 → large84),
* solves them with the MIP (HiGHS) and simulated annealing using default limits, and
* writes a summary table to ``tmp/benchmarks/summary.{csv,json}`` alongside per-solver
  assignment exports (``mip_assignments.csv``, ``sa_assignments.csv``).

CLI Options
-----------

``fhops bench suite`` accepts a number of flags:

* ``--scenario`` / ``-s`` — add one or more custom scenario YAML paths. When omitted the
  built-in scenarios are used.
* ``--time-limit`` — HiGHS time limit in seconds (default: 300).
* ``--sa-iters`` / ``--sa-seed`` — simulated annealing iteration budget and RNG seed.
* ``--driver`` — HiGHS driver (``auto``/``appsi``/``exec``) mirroring the ``solve-mip`` CLI.
* ``--include-mip`` / ``--include-sa`` — toggle individual solvers when running experiments.
* ``--out-dir`` — destination for summary files (default: ``tmp/benchmarks``).

Interpreting Outputs
--------------------

The summary CSV/JSON records, per scenario/solver pair:

* objective value (incorporating any objective weights),
* runtime (wall-clock seconds),
* number of assignments in the exported schedule,
* key KPIs: total production, mobilisation cost, sequencing violation counts, etc.

Example JSON snippet:

.. code-block:: json

   {
     "scenario": "minitoy",
     "solver": "sa",
     "objective": 9.5,
     "runtime_s": 0.02,
     "kpi_total_production": 42.0,
     "kpi_mobilisation_cost": 65.0,
     "kpi_mobilisation_cost_by_machine": "{\"H2\": 65.0}",
     "kpi_sequencing_violation_count": 0
   }

Assignments are stored under ``<out-dir>/<scenario>/<solver>_assignments.csv``. Feed these into
``fhops evaluate`` or project-specific analytics notebooks to dig deeper.

Mobilisation KPIs now include ``kpi_mobilisation_cost_by_machine`` (JSON string) so you can
identify which machines drive the bulk of movement spend. The larger ``examples/large84`` scenario
demonstrates the effect at scale; the CLI example above runs the MIP solver alone to keep runtimes
bounded.

Regression Fixture
------------------

``tests/fixtures/benchmarks/minitoy_sa.json`` records the expected seed-42 SA output for the
minitoy scenario (200 iterations) and is exercised by ``tests/test_benchmark_harness.py``.
Use it as a reference when extending the harness or adjusting solver defaults.

Future Work
-----------

Phase 2 follow-up tasks include:

* integrating benchmarking plots into the documentation,
* adding Tabu/ILS runs as metaheuristics mature, and
* calibrating mobilisation penalties against GeoJSON distance inputs.
