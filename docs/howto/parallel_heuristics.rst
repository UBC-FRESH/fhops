Parallel Heuristic Workflows
=============================

This how-to explains how to leverage the optional parallelisation features added in Phase 2.

Multi-start Runs
----------------

``fhops solve-heur`` exposes ``--parallel-multistart`` to launch several SA runs in parallel and keep the best objective. The seeds/presets used are generated deterministically via :func:`fhops.optimization.heuristics.build_exploration_plan`::

    fhops solve-heur examples/med42/scenario.yaml --out tmp/med42.csv \
        --parallel-multistart 8 --parallel-workers 4 --batch-neighbours 4 \
        --telemetry-log tmp/multistart.jsonl

Each run logs a telemetry record (``run_id``, ``seed``, ``preset``) plus a summary entry listing the best run. The CLI automatically falls back to a single run if any worker crashes.

Batched Neighbour Evaluation
----------------------------

``--batch-neighbours`` samples multiple candidates per iteration. ``--parallel-workers`` controls the threadpool size for scoring these candidates (default 1). Sequential scoring remains the default because profiling showed limited speedups on current workloads.

API Reference
-------------

- :func:`fhops.optimization.heuristics.solve_sa` – now accepts ``batch_size`` and ``max_workers`` parameters.
- :func:`fhops.optimization.heuristics.run_multi_start`` – orchestrates multiple solver runs, emitting telemetry and returning the best solution.
- :func:`fhops.optimization.heuristics.build_exploration_plan`` – helper for deterministic seeds/presets when constructing multi-start workloads.

Profiling Notes
---------------

Benchmarks (``tmp/sa_batch_profile.csv`` and ``tmp/sa_batch_profile_long.csv``) show that threaded evaluation adds ~5–6× overhead on minitoy/med42/large84, so keep parallel options opt-in until future workloads justify them.

