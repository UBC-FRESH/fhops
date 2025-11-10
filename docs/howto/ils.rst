Iterated Local Search How-to
============================

The Iterated Local Search (ILS) solver reuses the operator registry to alternate between local
improvement phases and diversification perturbations. It sits between simulated annealing and the
Tabu prototype: deterministic local search with optional hybrid MIP restarts.

Basic Usage
-----------

.. code-block:: bash

    fhops solve-ils examples/minitoy/scenario.yaml \
        --out tmp/minitoy_ils.csv \
        --iters 250 --perturbation-strength 3 --stall-limit 10 \
        --batch-neighbours 4 --parallel-workers 4 \
        --telemetry-log tmp/ils_runs.jsonl

Key options:

``--perturbation-strength``
    Number of perturbation steps executed after each local search cycle (default: ``3``).

``--stall-limit``
    Non-improving iterations before perturbation/restart logic triggers (default: ``10``).

``--hybrid-use-mip`` / ``--hybrid-mip-time-limit``
    Opt-in hybrid path that launches a time-boxed MIP solve once stalls exceed the limit. Results
    are converted back into the heuristic schedule when feasible.

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

Benchmarks
----------

``fhops bench suite --include-ils`` emits additional ``ils`` rows alongside SA/Tabu/MIP results.
Current runs (minitoy/med42/large84, 250 iterations) show ILS closing small gaps faster than Tabu
while remaining slightly behind SA. The solver stays opt-in until we complete the hybrid warm-start
investigation documented in ``notes/metaheuristic_roadmap.md``.
