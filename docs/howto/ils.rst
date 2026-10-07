Iterated Local Search How-to
============================

The Iterated Local Search (ILS) solver reuses the operator registry to alternate between local
improvement phases and diversification perturbations. It sits between simulated annealing and the
Tabu prototype: deterministic local search with optional hybrid MIP restarts.

Basic Usage
-----------

.. code-block:: bash

    fhops solve-ils examples/tiny7/scenario.yaml \
        --out tmp/tiny7_ils.csv \
        --iters 250 --perturbation-strength 3 --stall-limit 10 \
        --batch-neighbours 4 --parallel-workers 4 \
        --telemetry-log tmp/ils_runs.jsonl

Key options:

``--perturbation-strength``
    Number of perturbation steps executed after each local search cycle (default: ``3``).

``--stall-limit``
    Non-improving iterations before perturbation/restart logic triggers (default: ``10``).

``--hybrid-use-mip`` / ``--hybrid-mip-time-limit``
    Opt-in hybrid path: each time stalls reach the limit, the operational MILP
    (:func:`fhops.model.milp.driver.solve_operational_milp`, HiGHS, time-boxed by
    ``--hybrid-mip-time-limit`` seconds, same objective weights as the ILS run) is solved with the
    best ILS schedule as its incumbent — a genuine MIP start through Pyomo's ``appsi_highs``
    interface (see :doc:`mip_warm_starts`). The MILP schedule replaces the ILS best only when it
    scores higher under the heuristic evaluator; a MILP solve without a solution keeps the ILS
    schedule. (Before FHOPS 1.0.1 this step solved the legacy day-level MIP without an incumbent,
    which is infeasible for scenarios with loader roles; #104, #127.)

``--batch-neighbours`` / ``--parallel-workers``
    Reuse the batched neighbour generation/evaluation infrastructure from SA. Defaults keep the
    sequential single-thread behaviour.

Telemetry
---------

ILS telemetry mirrors SA metadata (initial/best score, operator weights/stats) and adds:

* ``perturbations`` – diversification steps executed.
* ``restarts`` – restarts triggered via hybrid or perturbation.
* ``improvement_steps`` – count of local search improvements.
* ``hybrid_use_mip`` / ``hybrid_mip_time_limit`` – hybrid configuration echoed for diagnostics.
* ``hybrid_mip`` (result ``meta`` only, when the hybrid step is enabled) – one record per hybrid
  MILP solve: ``iteration``, ``seed_score``, ``outcome``, ``objective``, ``solver_error``,
  ``warm_start_accepted``, ``warm_start_seeded_slots``, ``hybrid_score`` and ``adopted``.

Benchmarks
----------

``fhops bench suite --include-ils`` emits additional ``ils`` rows alongside SA/Tabu/MIP results.
Current runs (tiny7/med42/large84, 250 iterations) show ILS closing small gaps faster than Tabu
while remaining slightly behind SA. The solver stays opt-in until we complete the hybrid warm-start
investigation documented in ``notes/metaheuristic_roadmap.md``.
