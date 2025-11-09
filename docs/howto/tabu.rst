Tabu Search How-to
===================

The Tabu Search prototype provides an alternative to simulated annealing for diversification-heavy workloads.

Basic Usage
-----------

.. code-block:: bash

    fhops solve-tabu examples/minitoy/scenario.yaml \
        --out tmp/minitoy_tabu.csv \
        --iters 2000 --tabu-tenure 20 --stall-limit 300 \
        --batch-neighbours 4 --parallel-workers 4 \
        --telemetry-log tmp/tabu_runs.jsonl

Key options:

``--tabu-tenure``
    Length of the tabu list. ``0`` (default) picks ``max(10, #machines)``.

``--stall-limit``
    Maximum number of non-improving iterations before terminating early.

``--batch-neighbours`` / ``--parallel-workers``
    Reuse the batched neighbour evaluation infrastructure from SA. Defaults keep sequential scoring.

Telemetry
---------

Telemetry records mirror SA entries but add ``tabu_tenure`` and ``stall_limit`` fields. Multi-start telemetry currently applies only to SA; Tabu emits a single record per run.

Benchmarks
----------

Refer to ``tmp/tabu_bench/summary.csv`` (generated via ``fhops bench suite --include-tabu``) and ``tmp/sa_batch_profile_long.csv`` for the latest profiling data. In current runs (minitoy/med42/large84, 500 iterations) Tabu lags behind SA, so the solver remains opt-in until further tuning.
