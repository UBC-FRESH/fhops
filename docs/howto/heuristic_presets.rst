Heuristic Presets & Registry Guide
==================================

This how-to explains how to configure FHOPS heuristics via operator presets, explicit weight
overrides, and opt-in features such as parallel evaluation, Iterated Local Search (ILS), and
Tabu Search. Use it alongside the CLI reference (:doc:`../reference/cli`) and benchmarking how-to
(:doc:`benchmarks`) to design repeatable tuning workflows.

Preset Overview
---------------

Operator presets provide named weight profiles for the heuristic registry. Each preset targets a
specific behaviour:

``default``
    Balanced swap/move operators with advanced moves disabled (baseline behaviour).
``explore``
    Enables advanced neighbourhoods (block insertion, cross exchange, mobilisation shake) with
    moderate weights to diversify search.
``mobilisation``
    Prioritises mobilisation shake moves for distance-constrained scenarios.
``stabilise``
    Dampens advanced operators and boosts intra-machine moves to consolidate schedules.

List presets with:

.. code-block:: bash

    fhops solve-heur ... --list-operator-presets

Applying Presets
----------------

Use ``--operator-preset`` to enable one or more presets. When multiple presets are supplied they are
merged in order; later presets overwrite weights from earlier ones.

.. code-block:: bash

    # Balanced baseline
    fhops solve-heur examples/minitoy/scenario.yaml --out tmp/minitoy_sa.csv \
        --operator-preset default

    # Diversification-heavy profile
    fhops solve-heur examples/med42/scenario.yaml --out tmp/med42_explore.csv \
        --operator-preset explore --operator-preset mobilisation

Explicit Overrides
------------------

Presets can be combined with ``--operator`` (to restrict the enabled set) and
``--operator-weight name=value`` overrides. Overrides apply after presets.

.. code-block:: bash

    fhops solve-heur examples/large84/scenario.yaml --out tmp/large84_custom.csv \
        --operator-preset explore \
        --operator-weight mobilisation_shake=0.5 \
        --operator swap --operator move --operator block_insertion

Parallel & Advanced Features
----------------------------

The registry-backed operators work across all heuristics. Opt-in features share the same options:

* **Batched neighbours**: ``--batch-neighbours N`` samples multiple candidates per iteration.
  Pair with ``--parallel-workers`` to evaluate them concurrently.
* **Parallel multi-start**: ``--parallel-multistart K`` launches multiple SA runs; use
  ``--parallel-workers`` to control worker concurrency. Telemetry logs record per-run stats.
* **Iterated Local Search**: ``fhops solve-ils`` reuses presets/weights. Parallel knobs mirror SA.
* **Tabu Search**: ``fhops solve-tabu`` accepts the same preset/weight flags while adding
  Tabu-specific parameters (tenure, stall limit).
* **Profiles**: ``fhops solve-heur --profile explore`` applies a bundled configuration (operator
  presets, batching, multi-start). List options via ``fhops solve-heur --list-profiles``; explicit CLI
  flags still override profile defaults.

Reference the dedicated how-tos for ILS and Tabu when tuning those solvers.
* :doc:`parallel_heuristics` details the opt-in parallel execution pathways shared across heuristics.
* :doc:`ils` and :doc:`tabu` dive into solver-specific parameters built on top of the registry.

Operator Catalogue
------------------

All heuristics share the registry operators:

``swap``
    Exchange assignments between machines/day-shifts.
``move``
    Reassign a block within the same machine to a different day/shift.
``block_insertion``
    Insert a block into a new machine/shift slot, swapping out the previous occupant as needed.
``cross_exchange``
    Cross-machine swap with additional feasibility checks (windows, locks, mobilisation impacts).
``mobilisation_shake``
    Diversification move biased toward mobilisation-heavy adjustments (opt-in via presets).

Weights set to ``0`` disable the operator.

Telemetry & Benchmarking
------------------------

Heuristic runs emit per-operator telemetry (proposals, acceptances, weights). Combine presets and
overrides with telemetry logs to spot under-performing operators:

.. code-block:: bash

    fhops solve-heur ... --telemetry-log tmp/heuristics.jsonl --show-operator-stats

Benchmark summaries include comparison columns (best heuristic solver, objective gaps, runtime
ratios). Generate visualisations with:

.. code-block:: bash

    fhops bench suite --include-ils --include-tabu --no-include-mip --out-dir tmp/bench_compare
    python scripts/render_benchmark_plots.py tmp/bench_compare/summary.csv

Next Steps
----------

* Use the :doc:`benchmarks` how-to to interpret comparison metrics and plots.
* See ``notes/metaheuristic_hyperparam_tuning.md`` for the long-term tuning roadmap.
* When presets change, rerun ``fhops bench suite`` and regenerate plots with ``scripts/render_benchmark_plots.py`` before updating documentation.
* For CLI flag details, refer back to :doc:`../reference/cli`.
