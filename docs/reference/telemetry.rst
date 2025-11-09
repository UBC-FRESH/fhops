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
    ``sa`` for simulated annealing (future solvers may log here as well).

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

Usage Notes
-----------

- Logs are append-only; use tooling such as ``jq`` or pandas to analyse historical performance.
- Operators with frequently low acceptance rates may warrant weight adjustments or new presets.
- Combine logs with the hyperparameter tuning plan (``notes/metaheuristic_hyperparam_tuning.md``) to drive future ML/LLM-based schedulers.
