Telemetry-Driven Tuning
=======================

The hyperparameter tuning CLIs (`fhops tune-random`, `fhops tune-grid`, `fhops tune-bayes`)
log every run to JSONL and automatically mirror the same data into
``telemetry/runs.sqlite``. This guide walks through a lightweight sweep,
generating a tuning report, and interpreting the resulting artefacts.

Prerequisites
-------------

* FHOPS installed in your virtual environment (``pip install -e .[dev]``).
* The example scenarios shipped under ``examples/`` (installed with the project).

Step 1 – Collect Telemetry
--------------------------

Pick a directory for the telemetry bundle and point each tuning command at the
same ``--telemetry-log`` path. FHOPS will create the JSONL file plus a mirrored
SQLite database alongside it.

.. code-block:: bash

   mkdir -p tmp/tuner-demo

   fhops tune-random examples/minitoy/scenario.yaml \
       --runs 2 \
       --iters 150 \
       --telemetry-log tmp/tuner-demo/runs.jsonl

   fhops tune-grid examples/minitoy/scenario.yaml \
       --batch-size 1 \
       --batch-size 2 \
       --preset balanced \
       --preset explore \
       --iters 150 \
       --telemetry-log tmp/tuner-demo/runs.jsonl

   fhops tune-bayes examples/minitoy/scenario.yaml \
       --trials 3 \
       --iters 150 \
       --telemetry-log tmp/tuner-demo/runs.jsonl

You can now supply **scenario bundles** instead of individual paths. The built-in
aliases ``baseline`` (minitoy + med42), ``synthetic`` (small/medium/large tiers),
and the tier-specific aliases (``synthetic-small`` etc.) expand to their component
scenarios. Point the tuning commands at a bundle with ``--bundle``:

.. code-block:: bash

   fhops tune-random --bundle baseline \
       --runs 1 \
       --iters 150 \
       --telemetry-log tmp/tuner-demo/runs.jsonl

   fhops tune-bayes --bundle synthetic-small \
       --trials 2 \
       --iters 150 \
       --telemetry-log tmp/tuner-demo/runs.jsonl

Bundle specs also accept ``alias=path`` so you can wire custom manifests or directories
containing ``metadata.yaml``. See :ref:`telemetry_bundle_aliases` below for details.

After those commands complete you will have:

* ``tmp/tuner-demo/runs.jsonl`` — append-only log of each run.
* ``tmp/tuner-demo/runs.sqlite`` — structured tables (`runs`, `run_metrics`,
  `run_kpis`, and `tuner_summaries`) that mirror the JSONL payload.
* ``tmp/tuner-demo/steps/<run_id>.jsonl`` — optional per-step logs (only when
  the solver emits granular snapshots).

Step 2 – Generate a Comparison Report
-------------------------------------

Use the ``fhops telemetry report`` subcommand to aggregate the SQLite store into
machine-readable (CSV) and human-readable (Markdown) summaries:

.. code-block:: bash

   fhops telemetry report tmp/tuner-demo/runs.sqlite \
       --out-csv tmp/tuner-demo/tuner_report.csv \
       --out-markdown tmp/tuner-demo/tuner_report.md

The command prints a Markdown table to stdout by default; passing ``--out-*``
flags writes the same content to disk. The generated CSV columns include
aggregated statistics (best/mean objective, run counts) plus any matching
``tuner_summaries`` rows added by the CLI commands. Continuous integration
executes this pipeline for **minitoy** and **med42** so the published artefacts
already contain multiple scenarios.

Add ``--out-summary-csv`` / ``--out-summary-markdown`` to emit a per-scenario
scoreboard showing the best algorithm/objective for each report label (baseline,
experiment, etc.). The summary files are ideal for dashboard badges or CI checks
because they surface the top performer per scenario without manually inspecting
the full table.

Sample Output
-------------

Markdown table (``tmp/tuner-demo/tuner_report.md``) for a short sweep:

.. code-block:: text

   | Algorithm | Scenario | Best Objective | Mean Objective | Runs | Summary Best | Configurations |
   | --- | --- | --- | --- | --- | --- | --- |
   | bayes | FHOPS MiniToy | 8.125 | 8.125 | 1 | 8.125 | 3 |
   | grid | FHOPS MiniToy | 7.750 | 7.438 | 4 | 7.750 | 4 |
   | random | FHOPS MiniToy | 7.375 | 6.812 | 2 | 7.375 | 2 |

Step 3 – Iterate
----------------

* Use the CSV file for deeper analysis in pandas/Polars or to drive dashboards.
* Inspect the Markdown report (or the uploaded CI artefact) in code reviews to
  track how a branch affects tuning performance.
* Because the report operates directly on the SQLite store, you can rerun it at
  any time without regenerating telemetry.

Step 4 – Compare Multiple Reports
---------------------------------

To track changes across branches or nightly runs, use
``scripts/analyze_tuner_reports.py`` to merge several ``tuner_report.csv`` files
and compute deltas against a baseline:

.. code-block:: bash

   python scripts/analyze_tuner_reports.py \
       baseline=tmp/ci-telemetry/tuner_report.csv \
       experiment=tmp/local/tuner_report.csv \
       --out-markdown tmp/comparison.md \
       --out-csv tmp/comparison.csv \
       --out-chart tmp/comparison.html

The script aligns records on (algorithm, scenario) and appends ``best_delta_*``
columns showing the improvement relative to the first report label.
Passing ``--out-chart`` generates an Altair HTML visualization of best objectives per algorithm.

Historical Trends
-----------------

Keep dated copies of ``tuner_report.csv`` snapshots (for example, download the
``telemetry-report`` artifact from multiple CI runs) and place them in a single
directory. Then call ``analyze_tuner_reports.py`` with ``--history-dir`` to
produce a longitudinal view:

.. code-block:: bash

   python scripts/analyze_tuner_reports.py \
       --report latest=tmp/ci-telemetry/tuner_report.csv \
       --history-dir docs/examples/analytics/data/tuner_reports \
       --out-history-csv tmp/history.csv \
       --out-history-markdown tmp/history.md \
       --out-history-chart tmp/history.html

The generated history table lists the best/mean objectives per algorithm and
scenario across snapshots (derived from the filename stem). When the source
telemetry includes extra KPIs (total production, mobilisation cost, downtime
hours, weather severity, utilisation ratios) they appear as additional columns in
the history summary. The optional Altair chart highlights objective trends at a
glance.

Continuous integration already copies the minitoy smoke sweep into the
``history/`` subdirectory of the ``telemetry-report`` artifact using UTC
timestamps, so you can download successive runs and feed them directly to the
history command. The workflow also generates ``history_summary.{csv,md,html}``
via ``analyze_tuner_reports.py --history-dir`` so you can inspect trends
immediately after downloading the artifact.

If your repository enables GitHub Pages for the documentation or telemetry site,
the CI workflow publishes the HTML history to
``https://<org>.github.io/<repo>/telemetry/history_summary.html``. The README links
to the live page (see the FHOPS reference deployment at
``https://ubc-fresh.github.io/fhops/telemetry/history_summary.html``), so you can
share the same chart without downloading artifacts.

Delta Snapshot Summary
----------------------

For a quick “what changed since last snapshot” view, pass ``--out-history-delta-*`` when
invoking ``analyze_tuner_reports.py``. The CI workflow already produces
``history_delta.{csv,md}``, summarising the latest vs. previous snapshot for objectives and KPIs.
Example command:

.. code-block:: bash

   python scripts/analyze_tuner_reports.py \
       --history-dir docs/examples/analytics/data/tuner_reports \
       --out-history-delta-csv tmp/history_delta.csv \
       --out-history-delta-markdown tmp/history_delta.md

.. figure:: ../examples/analytics/data/tuner_reports/history_summary.png
   :alt: Sample telemetry history chart
   :align: center

   Sample telemetry history derived from the committed demo data. Actual CI
   artefacts contain the latest minitoy and med42 measurements.

The delta outputs are versioned alongside the HTML chart. When CI finishes it
emits ``history_delta.{csv,md}`` (and any optional PNG/HTML charts you request),
mirroring the GitHub Pages snapshot. Monitoring those files or wiring them into a
status badge is a simple way to highlight regressions without manually opening the
full report.

Automated Sweeps
----------------

Use ``scripts/run_tuning_benchmarks.py`` to orchestrate random/grid/Bayesian sweeps over
the canonical bundles and emit aggregate reports in one go:

.. code-block:: bash

   python scripts/run_tuning_benchmarks.py \
       --bundle baseline \
       --tier short --tier medium \
       --out-dir tmp/tuning-benchmarks \
       --random-runs 2 \
       --grid-iters 150 \
       --bayes-trials 4

The script resets (or appends to) the telemetry log, runs the requested tuners, calls
``fhops telemetry report`` to generate ``tuner_report.{csv,md}``, and invokes
``analyze_tuner_reports.py`` with ``--out-summary-*`` so you get a concise per-scenario
leaderboard. Adjust ``--bundle`` and tuner-specific options to suit larger sweeps or
CI smoke passes. Repeating ``--tier`` runs each budget tier sequentially and forwards
``--tier-label`` to the CLI tuners so telemetry collectors can pivot results by tier.
Include ``--tuner ils --tuner tabu`` (or rely on plan defaults) to sweep Iterated Local Search
and Tabu Search alongside the simulated annealing tuners; use ``--ils-runs`` / ``--ils-iters`` and
``--tabu-runs`` / ``--tabu-iters`` to override the tier budgets when experimenting locally.

In addition to the per-scenario summaries, the script now emits:

* ``tuner_comparison.{csv,md}`` — per-scenario/per-algorithm table with best objective, mean objective, mean runtime, and delta vs. the scenario leader.
* ``tuner_leaderboard.{csv,md}`` — aggregate win rates, average metrics, and deltas per algorithm across all scenarios.

Benchmark plans
~~~~~~~~~~~~~~~

Use ``--plan`` to reuse the curated budgets across bundles:

.. list-table::
   :header-rows: 1
   :widths: 20 35 15 30

   * - Plan
     - Coverage
     - Default tiers
     - Tier overrides (random / grid / bayes)
   * - ``baseline-smoke``
     - ``examples/minitoy`` + ``examples/med42``
     - ``short``
     - ``3 × 250 iters`` / ``(balanced, explore) × batch {1,2} × 250`` / ``30 trials × 250``
   * - ``synthetic-smoke``
     - ``examples/synthetic/{small,medium,large}``
     - ``short``
     - ``3 × 300 iters`` / ``(balanced, explore) × batch {1,2} × 300`` / ``30 trials × 300``
   * - ``full-spectrum``
     - baseline + synthetic bundles
     - ``short``, ``medium``
     - ``medium`` tier extends to ``4 × 450 iters`` / ``(balanced, explore) × batch {1,2} × 450`` / ``45 trials × 450``

Tier defaults (short/medium/long) are embedded in the runner; omit overrides to pick up
``2 × 150`` / ``3 × 300`` / ``5 × 600`` iteration schedules for random/grid/bayesian respectively.
Budgets deliver a 3–5 minute sweep locally on ``short``; bump to ``medium`` or ``long`` when you need
convergence traces for modelling. Override any option (e.g., ``--random-runs``) as needed.
When running full benchmark suites on shared hardware, pin at least 64 CPU cores to the job and cap
per-run RSS to ~8 GB to avoid starving other workloads while we expand the benchmark matrix.
ILS/Tabu inherit the same tier labels: ``short`` executes two restarts with ~200/1 200 iterations,
``medium`` scales to three restarts with ~350/2 000 iterations, and ``long`` extends to five restarts
(ILS enables the hybrid MIP warm start) with ~700/3 000 iterations. Adjust the respective ``--ils-*``
and ``--tabu-*`` flags when you need lighter smoke runs or deeper convergence traces.

Heuristic parameter catalogue
-----------------------------

Use the table below to map CLI flags to the tuning surface. The benchmark tiers above seed default
budgets; you can override any parameter when experimenting locally or defining Optuna search spaces.

.. list-table::
   :header-rows: 1
   :widths: 22 35 25 18

   * - Layer
     - Parameters / flags
     - Typical range / notes
     - Tier coverage
   * - Simulated Annealing (``solve-heur``, ``tune-random/grid/bayes``)
     - ``--iters`` (150/300/600), ``--temperature0`` (50–500), ``--cooling-rate`` (0.90–0.999)
     - Iteration horizon + geometric cooling schedule
     - short/medium/long
   * -
     - ``--batch-neighbours`` (1–5), ``--parallel-workers`` (1–4)
     - Batched neighbour evaluation with optional thread pool
     - grid presets cover batch; medium/long enable workers
   * -
     - ``--operator``, ``--operator-weight``, ``--operator-preset`` (balanced/explore/mobilisation/agentic)
     - Operator activation/weights; searchers toggle presets or sample weights
     - All tiers via grid/random/bayes
   * -
     - ``--multi-start``, profile extras (reheating, schedule families)
     - Multi-start counts, seed progression, reheating cadence
     - Enabled in medium/long profiles; agentic tuner mutates via ``tuner_meta``
   * - Iterated Local Search (``solve-ils``/tuning drivers)
     - ``--iters`` (200/350/700)
     - Outer perturbation/local-search cycles
     - All tiers
   * -
     - ``--perturbation-strength`` (1–6), ``--stall-limit`` (8–20)
     - Diversification vs. exploitation
     - Random/Bayesian search + medium/long defaults
   * -
     - ``--hybrid-use-mip``, ``--hybrid-mip-time-limit`` (30–180 s)
     - Hybrid restart when stalled
     - Long tier default, optional elsewhere
   * -
     - Operator/preset flags, batching options
     - Shares registry knobs with SA so presets stay aligned
     - All tiers
   * - Tabu Search (``solve-tabu``/tuning drivers)
     - ``--iters`` (1 200/2 000/3 000)
     - Search horizon per tier
     - All tiers
   * -
     - ``--tabu-tenure`` (auto → machine count, sweep 20–120), ``--stall-limit`` (150–250)
     - List length & stagnation window
     - Random/Bayesian search + tier overrides
   * -
     - Operator/preset weights, batching
     - Mirrors SA/ILS for cross-tuner parity
     - All tiers
   * - Tuner budgets
     - Random: ``--runs``, ``--iters``; Grid: ``--iters``, ``--batch-size``, ``--preset``; Bayes: ``--trials``, ``--iters``
     - Tier presets define default budgets; plans override for smokes/full suites
     - Documented above
   * - Meta / agentic extensions
     - Telemetry-derived features (gap slope, acceptance trajectory, scenario descriptors)
     - Stored in ``tuner_meta`` / ``context`` for future AutoML/LLM agents
     - Planned Phase 3 enhancement

CI publishes the latest summary tables to GitHub Pages; check
``https://<org>.github.io/<repo>/telemetry/latest_tuner_summary.md`` (per-scenario
leaderboard) and ``latest_history_summary.md`` (delta vs. previous snapshot) to spot regression
signals without grabbing artefacts.
The comparison and leaderboard tables are also available at
``.../latest_tuner_comparison.{md,csv}`` and ``.../latest_tuner_leaderboard.{md,csv}``.
Bundle-specific variants (``tuner_comparison_baseline.*``, ``tuner_leaderboard_synthetic.*``) are published alongside a difficulty table (``tuner_difficulty*.{md,csv}``) containing best-algorithm deltas, second-best gaps, and MIP gaps when available.

Convergence metrics
-------------------

Once sweeps finish, derive time-to-quality signals with
``scripts/analyze_tuner_reports.py``. Provide the generated report (or directory) and
the telemetry log so the script can inspect step logs:

.. code-block:: bash

   python scripts/analyze_tuner_reports.py \
       --report tmp/tuning-benchmarks/tuner_report.csv \
       --telemetry-log tmp/tuning-benchmarks/telemetry/runs.jsonl \
       --out-convergence-csv tmp/tuning-benchmarks/convergence_runs.csv \
       --out-convergence-summary-csv tmp/tuning-benchmarks/convergence_summary.csv \
       --out-convergence-summary-markdown tmp/tuning-benchmarks/convergence_summary.md

The summary tallies, per scenario/algorithm/tier, how many runs reach a ≤1 % gap versus
the recorded MIP optimum, plus the mean/median iteration counts required. Step logs
must be present (the runner writes them to ``telemetry/steps/<run_id>.jsonl``) and each
scenario needs a matching ``solve-mip`` baseline in the telemetry store. Adjust
``--convergence-threshold`` if you need a different gap target.

Tuner metadata summary
~~~~~~~~~~~~~~~~~~~~~~

Runs now embed high-level metadata (algorithm, budgets, progress) via ``tuner_meta``. Use
``scripts/summarize_tuner_meta.py`` to inspect the aggregated view:

.. code-block:: bash

   python scripts/summarize_tuner_meta.py telemetry/runs.sqlite \
       --out-markdown tmp/tuner_meta_summary.md

The summary table lists algorithms, number of runs, unique scenarios, and representative budgets.

.. _telemetry_bundle_aliases:

Bundle Aliases
--------------

The tuning commands accept ``--bundle`` to expand a manifest of scenarios. FHOPS ships
the following aliases:

* ``baseline`` → ``examples/minitoy/scenario.yaml`` and ``examples/med42/scenario.yaml``
* ``synthetic`` → the ``small``, ``medium``, and ``large`` synthetic tiers
* ``synthetic-small`` / ``synthetic-medium`` / ``synthetic-large`` → individual synthetic tiers
* ``minitoy`` / ``med42`` / ``large84`` → convenience handles for the built-in evaluation set

Aliases are case-insensitive and you can specify multiple ``--bundle`` flags in a single
command. For custom bundles, pass ``alias=/path/to/metadata.yaml`` (or the directory
containing ``metadata.yaml``). Each entry inside the metadata file is resolved relative to
its location, so ``examples/synthetic/metadata.yaml`` gives you ``synthetic-small`` et al.

Bundle members are logged in telemetry context as ``bundle`` / ``bundle_member`` and appear
in the aggregated ``tuner_summary`` records as ``bundle:member`` keys. This keeps the
history/delta tooling aware of the scenario family without changing existing report formats.

CI Automation
-------------

The main CI workflow runs a nightly smoke sweep on ``examples/minitoy`` and
uploads ``tmp/ci-telemetry/tuner_report.{csv,md}`` as build artefacts. Use those
artefacts as a baseline when evaluating new heuristics or tuning strategies.

For longer experiments (e.g., synthetic bundles or larger iteration budgets),
reuse the same workflow with adjusted ``--runs`` / ``--trials`` / ``--iters``
parameters and point the telemetry log at a scenario-specific directory.

Downloading CI Reports
----------------------

Each CI run exposes a ``telemetry-report`` artefact containing the latest
``tuner_report.{csv,md}`` files alongside the raw telemetry bundle. To download:

* Via the GitHub web UI: open the completed workflow run, expand the **Artifacts**
  section, and click ``telemetry-report`` to fetch the zip file.
* Via the command line (requires `gh`):

  .. code-block:: bash

     gh run download --repo <owner>/<repo> --name telemetry-report --dir tmp/ci-telemetry

After extraction, inspect ``tuner_report.md`` directly or load
``tuner_report.csv`` into pandas/Polars for deeper analysis.
