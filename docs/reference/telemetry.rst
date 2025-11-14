Telemetry Logging
=================

Simulated annealing runs can emit structured telemetry so that future tuning (manual, LLM-assisted,
or automated) can analyse performance. Use ``--telemetry-log PATH`` with either
``fhops solve-heur`` or ``fhops bench suite`` to append newline-delimited JSON records::

    fhops solve-heur examples/minitoy/scenario.yaml --out tmp/result.csv \
        --telemetry-log tmp/telemetry.jsonl --show-operator-stats

Schema
------

Each JSON record includes the following fields:

``timestamp`` (str)
    ISO8601 UTC timestamp when the entry was written.

``source`` (str)
    Command that generated the entry (``solve-heur`` or ``bench-suite``).

``scenario`` (str) / ``scenario_path`` (str)
    Scenario name and file path.

``solver`` (str)
    Identifies the solver (``sa``, ``ils``, ``tabu``). When omitted the record came from ``solve-heur`` without specifying an algorithm (legacy).

``seed`` (int), ``iterations`` (int)
    Parameters used for the run.

``objective`` (float)
    Final objective reported by the solver.

``kpis`` (object)
    Snapshot of computed KPIs (mobilisation cost, total production, etc.).

``operators_config`` (object)
    Final operator weight configuration used for the run.

``operators_stats`` (object)
    Per-operator telemetry with the following fields:

    - ``proposals``: number of neighbour proposals emitted.
    - ``accepted``: number of accepted neighbours.
    - ``skipped``: times the operator returned ``None`` (e.g., infeasible move).
    - ``weight``: effective weight used for selection.
    - ``acceptance_rate``: ``accepted / proposals`` (0 when proposals is 0).

Example
~~~~~~~

.. code-block:: json

   {
    "timestamp": "2025-11-09T05:31:42.972801",
    "source": "solve-heur",
    "scenario": "FHOPS MiniToy",
    "scenario_path": "examples/minitoy/scenario.yaml",
    "solver": "sa",
     "seed": 42,
     "iterations": 200,
     "objective": 13.0,
    "kpis": {"total_production": 45.5, "mobilisation_cost": 65.0, "...": "..."},
    "operators_config": {"swap": 1.0, "move": 1.0},
    "operators_stats": {
      "swap": {
        "proposals": 200.0,
        "accepted": 200.0,
        "skipped": 0.0,
        "weight": 1.0,
        "acceptance_rate": 1.0
      },
      "move": {
        "proposals": 200.0,
        "accepted": 200.0,
        "skipped": 0.0,
        "weight": 1.0,
        "acceptance_rate": 1.0
      }
    }
  }

Solver-specific fields
~~~~~~~~~~~~~~~~~~~~~~

- ILS entries echo diversification metadata: ``perturbations``, ``restarts``, ``improvement_steps``,
  ``stall_limit``, ``perturbation_strength``, and hybrid flags (``hybrid_use_mip``,
  ``hybrid_mip_time_limit``).
- Tabu entries include ``tabu_tenure`` and ``tabu_stall_limit``.

Usage Notes
-----------

- Logs are append-only; use tooling such as ``jq`` or pandas to analyse historical performance.
- Operators with frequently low acceptance rates may warrant weight adjustments or new presets.
- Combine logs with the hyperparameter tuning plan (``notes/metaheuristic_hyperparam_tuning.md``) to drive future ML/LLM-based schedulers.
- Parallel options add ``batch_size``/``max_workers`` fields to single-run records. Multi-start telemetry logs per-run entries with ``run_id``/``preset`` and a summary record containing ``type: multi_start_summary``, ``best_run_id``, ``best_objective``, and ``runs_executed``.

CLI Reporting
-------------

Use the ``fhops telemetry report`` sub-command to aggregate the mirrored SQLite
store into CSV/Markdown summaries without re-running the tuners (CI and the
weekly analytics workflow both invoke this before deploying GitHub Pages)::

    fhops telemetry report telemetry/runs.sqlite \
        --out-csv tmp/tuner_report.csv \
        --out-markdown tmp/tuner_report.md

The command scans ``runs``, ``run_metrics``, ``run_kpis``, and
``tuner_summaries`` tables to surface best/mean objective values per algorithm
and scenario. See :doc:`../howto/telemetry_tuning` for a step-by-step guide and
``docs/reference/dashboards`` for the live links generated from these files.

Historical Trends
-----------------

Each CI run uploads three ready-made history artefacts under the
``telemetry-report`` bundle:

* ``history_summary.csv`` — tabular history of best/mean objectives for dated snapshots.
* ``history_summary.md`` — Markdown rendering of the same table.
* ``history_summary.html`` — Altair chart plotting best objective trends.
* ``history_delta.{csv,md}`` — latest vs. previous snapshot diff across objectives and key KPIs.

Download those files (or rerun ``analyze_tuner_reports.py --history-dir`` on a
local archive) to inspect performance trends without regenerating telemetry.
