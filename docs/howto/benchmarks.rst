Benchmarking Harness
====================

FHOPS ships sample scenarios in ``examples/`` (``minitoy``, ``med42``, ``large84``, and the synthetic
tiers under ``examples/synthetic/``) that cover
increasing planning horizons. The Phase 2 benchmarking harness runs the MIP and heuristic
solvers across these datasets, captures objectives/KPIs, and stores results for inspection.

Quick Start
-----------

.. code-block:: bash

   fhops bench suite --out-dir tmp/benchmarks
   fhops bench suite --scenario examples/minitoy/scenario.yaml --scenario examples/med42/scenario.yaml --out-dir tmp/benchmarks_med
   fhops bench suite --scenario examples/large84/scenario.yaml --out-dir tmp/benchmarks_large --time-limit 180 --include-sa False
   fhops bench suite --scenario examples/synthetic/small/scenario.yaml --out-dir tmp/benchmarks_synth --sa-iters 200 --include-mip False
   fhops bench suite --include-ils --include-tabu --out-dir tmp/benchmarks_compare

This command:

* loads each bundled scenario (minitoy → med42 → large84 → synthetic-small by default),
* solves them with the MIP (HiGHS) and simulated annealing using default limits, and
* writes a summary table to ``tmp/benchmarks/summary.{csv,json}`` alongside per-solver
  assignment exports (``mip_assignments.csv``, ``sa_assignments.csv``).

CLI Options
-----------

``fhops bench suite`` accepts a number of flags:

* ``--scenario`` / ``-s`` — add one or more custom scenario YAML paths. When omitted the
  built-in scenarios are used.
* ``--time-limit`` — HiGHS time limit in seconds (default: 1800 for the large84 horizon).
  The quick-start example above still shows ``--time-limit 180`` for a smoke run; omit that flag to use the
  higher default when you want optimal certificates on the largest instance.
* ``--sa-iters`` / ``--sa-seed`` — simulated annealing iteration budget and RNG seed.
* ``--driver`` — MIP driver (``auto``/``highs-appsi``/``highs-exec``/``gurobi``/``gurobi-appsi``/``gurobi-direct``) mirroring the ``solve-mip`` CLI.
* ``--include-mip`` / ``--include-sa`` — toggle individual solvers when running experiments.
* ``--out-dir`` — destination for summary files (default: ``tmp/benchmarks``).

Optional Gurobi backend (Linux)
-------------------------------

HiGHS remains the default open-source MIP solver. If you have access to a Gurobi licence (e.g.
academic named-user), install the optional extras and register the licence before selecting
``--driver gurobi``:

.. code-block:: bash

   # install gurobipy alongside FHOPS
   pip install fhops[gurobi]

   # download the lightweight licence tools bundle (version shown is illustrative)
   wget https://packages.gurobi.com/lictools/licensetools13.0.0_linux64.tar.gz
   tar xvfz licensetools13.0.0_linux64.tar.gz

   # request your licence key (replace XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX)
   ./grbgetkey XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

   # accept the default path (typically $HOME/gurobi.lic) or specify a custom location
   # if you store the licence elsewhere, export GRB_LICENSE_FILE so gurobipy can find it:
   export GRB_LICENSE_FILE=/path/to/gurobi.lic

   # quick sanity check
   python -c "import gurobipy as gp; m = gp.Model(); m.setParam('OutputFlag', 0); m.optimize()"

Once the licence is active, any FHOPS command can use Gurobi by passing ``--driver gurobi`` (or the
other Gurobi driver variants). Without an available licence the CLI will fall back to HiGHS.

Interpreting Outputs
--------------------

The summary CSV/JSON records, per scenario/solver pair:

* objective value (incorporating any objective weights),
* runtime (wall-clock seconds),
* number of assignments in the exported schedule,
* key KPIs: total production, mobilisation cost, sequencing violation counts, etc.
* For SA runs, iteration budget and RNG seed are included to help compare tuning parameters across experiments.
* Comparison helpers:

  - ``solver_category`` labels exact vs heuristic solvers.
  - ``best_heuristic_solver`` / ``best_heuristic_objective`` identify the strongest heuristic per scenario.
  - ``objective_gap_vs_best_heuristic`` shows how far each solver trails the top heuristic (negative values mean the solver beats the best heuristic, e.g., MIP).
  - ``runtime_ratio_vs_best_heuristic`` reports runtime multiples relative to the quickest heuristic winner.

Shared KPI roll-up
------------------

.. include:: ../includes/softwarex/benchmark_kpis.rst

.. include:: ../includes/softwarex/benchmark_kpis_notes.rst

Interpretation tips:

* Positive gaps mean the solver under-performs the best heuristic; negative gaps indicate an improvement (common for MIP or exploratory heuristics).
* Runtime ratios greater than ``1`` are slower than the best heuristic; numbers below ``1`` are faster.
* Combine these columns with telemetry logs to pinpoint operators that drive under-performance.

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

Operator Telemetry
------------------

When running the suite with simulated annealing enabled, the summary CSV/JSON includes an
``operators_config`` column (final weights) and an ``operators_stats`` column (per-operator
telemetry). ``operators_stats`` is a JSON object recording proposals, accepted moves, skips, weights,
and acceptance rates for each registered operator. Example snippet:

.. code-block:: json

   {
     "swap": {"proposals": 200, "accepted": 200, "skipped": 0, "weight": 1.0, "acceptance_rate": 1.0},
     "move": {"proposals": 200, "accepted": 200, "skipped": 0, "weight": 1.0, "acceptance_rate": 1.0}
   }

Use ``--show-operator-stats`` with ``fhops solve-heur`` for a human-readable table, or parse the
benchmark summaries programmatically to monitor operator performance over time. Persistent telemetry
logs (``--telemetry-log``) append the same structure to a newline-delimited JSON file for long-term
analysis.

Visual Comparisons
------------------

The helper script ``scripts/render_benchmark_plots.py`` consumes a benchmark summary and renders
comparison charts for documentation. For example:

.. code-block:: bash

   fhops bench suite --include-ils --include-tabu --no-include-mip --out-dir tmp/bench_visuals
   python scripts/render_benchmark_plots.py tmp/bench_visuals/summary.csv --out-dir docs/_static/benchmarks

.. figure:: /_static/benchmarks/objective_gap_vs_best_heuristic.png
   :alt: Objective gap per heuristic solver

   Objective gap versus the best heuristic solver for each scenario (negative bars indicate the solver beats the current best heuristic).

.. figure:: /_static/benchmarks/runtime_ratio_vs_best_heuristic.png
   :alt: Runtime ratios per heuristic solver

   Runtime ratios relative to the best heuristic solver (values > 1.0 are slower).

.. note::
   Regenerate the comparison summary and plots after significant heuristic changes by rerunning
   ``fhops bench suite --include-ils --include-tabu`` and the plotting helper script.

Each assignment CSV includes ``machine_id``, ``block_id``, ``day``, and ``shift_id`` columns.
The shift label is derived from the scenario's shift calendar or timeline definition, enabling
sub-daily benchmarking and evaluation workflows.

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
