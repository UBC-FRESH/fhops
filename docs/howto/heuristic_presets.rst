Heuristic Presets & Registry Guide
==================================

This how-to explains how to configure FHOPS heuristics via operator presets, explicit weight
overrides, and opt-in features such as parallel evaluation, Iterated Local Search (ILS), and
Tabu Search. Use it alongside the CLI reference (:doc:`../reference/cli`) and benchmarking how-to
(:doc:`benchmarks`) to design repeatable tuning workflows.

Shared Solver Cheat Sheet
-------------------------

.. include:: ../includes/softwarex/heuristics_matrix.rst

.. include:: ../includes/softwarex/heuristics_notes.rst

Preset Overview
---------------

Operator presets provide named weight profiles for the heuristic registry. Each preset targets a
specific behaviour:

``balanced``
    Default mix: swap/move plus block insertion and cross exchange (0.6) with a moderate
    mobilisation shake (0.2).
``explore``
    Enables advanced neighbourhoods (block insertion, cross exchange, mobilisation shake) with
    moderate weights to diversify search.
``mobilisation``
    Prioritises mobilisation shake moves for distance-constrained scenarios.
``stabilise``
    Dampens advanced operators and boosts intra-machine moves to consolidate schedules.

List presets with:

.. code-block:: bash

    fhops bench suite --list-operator-presets

``fhops solve-heur``/``solve-ils``/``solve-tabu`` accept the same flag, but still require the
scenario argument and ``--out`` (nothing is solved or written), e.g.
``fhops solve-heur examples/tiny7/scenario.yaml --out tmp/unused.csv --list-operator-presets``.

Applying Presets
----------------

Use ``--operator-preset`` to enable one or more presets. When multiple presets are supplied they are
merged in order; later presets overwrite weights from earlier ones.

.. code-block:: bash

    # Balanced baseline
    fhops solve-heur examples/tiny7/scenario.yaml --out tmp/tiny7_sa.csv \
        --operator-preset balanced

    # Diversification-heavy profile
    fhops solve-heur examples/med42/scenario.yaml --out tmp/med42_explore.csv \
        --operator-preset explore --operator-preset mobilisation

Explicit Overrides
------------------

Presets can be combined with ``--operator`` (to restrict the enabled set) and
``--operator-weight name=value`` overrides. Overrides apply after presets. (Long-running: the default
2000 SA iterations on large84 take tens of minutes; add ``--iters 200`` for a quick check.)

.. code-block:: bash

    fhops solve-heur examples/large84/scenario.yaml --out tmp/large84_custom.csv \
        --operator-preset explore \
        --operator-weight mobilisation_shake=0.5 \
        --operator swap --operator move --operator block_insertion

Solver-Specific Parameters
--------------------------

All heuristics share the registry, but each solver exposes additional knobs alongside the preset
controls:

* **Simulated Annealing (`fhops solve-heur`)**

  - ``--sa-iters`` / ``--iters`` – iteration budget (default 5000).
  - ``--sa-seed`` / ``--seed`` – RNG seed for reproducible runs.
  - ``--batch-neighbours`` – proposals per iteration (pair with ``--parallel-workers`` to evaluate in parallel).
  - ``--parallel-multistart`` – launch multiple runs in parallel; each honours the same presets/weights.
  - ``--profile NAME`` – apply bundled configs (operators + batching). List via ``--list-profiles``.

* **Iterated Local Search (`fhops solve-ils`)**

  - ``--ils-iters`` – number of ILS iterations between perturbations.
  - ``--ils-seed`` – RNG seed.
  - ``--ils-batch-neighbours`` / ``--ils-workers`` – batched evaluation controls.
  - ``--ils-perturbation-strength`` – number of random moves during perturbation phases.
  - ``--ils-stall-limit`` – iterations without improvement before perturbing.
  - ``--ils-hybrid-use-mip`` / ``--ils-hybrid-mip-time-limit`` – optional MIP warm start when a small budget can improve the seed.

* **Tabu Search (`fhops solve-tabu`)**

  - ``--tabu-iters`` – number of iterations.
  - ``--tabu-seed`` – RNG seed (controls candidate sampling).
  - ``--tabu-tenure`` – explicit tabu tenure (0 = auto).
  - ``--tabu-stall-limit`` – restarts when no improvement occurs.
  - ``--tabu-batch-neighbours`` / ``--tabu-workers`` – batched move evaluation.

All three share ``--operator``, ``--operator-weight``, ``--operator-preset``, and ``--profile`` so you can keep
the same operator mix while experimenting with solver parameters. The shortcut ``fhops bench suite`` wires
these flags through ``--sa-*``, ``--ils-*``, and ``--tabu-*`` options when comparing solvers side-by-side.

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
* **Profiles**: ``fhops solve-heur ... --profile explore`` applies a bundled configuration (operator
  presets, batching, multi-start). List options via ``fhops bench suite --list-profiles`` (``fhops
  solve-heur`` also accepts ``--list-profiles`` but still requires a scenario argument and ``--out``);
  explicit CLI flags still override profile defaults.

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
ratios). Generate visualisations with (long-running: all default scenarios, default budgets):

.. code-block:: bash

    fhops bench suite --include-ils --include-tabu --no-include-mip --out-dir tmp/bench_compare
    python scripts/render_benchmark_plots.py tmp/bench_compare/summary.csv

When you add ``--compare-preset`` the benchmark suite replays the same scenario with multiple preset
labels and records the results in ``preset_label``. The summary also embeds two JSON blobs:

``operators_config``
    Final weight mapping for the run (after presets + overrides).
``operators_stats``
    Per-operator telemetry (``proposals``, ``accepted``, ``skipped``, ``weight``, ``acceptance_rate``).

Inspect them directly with ``jq`` or load them into Pandas for analysis (long-running: all default
scenarios, including the MILP; add ``--no-include-mip`` or ``--scenario`` for a quick run):

.. code-block:: bash

    fhops bench suite --compare-preset explore --compare-preset mobilisation \
        --include-ils --include-tabu --out-dir tmp/bench_compare
    python - <<'PY'
    import pandas as pd
    df = pd.read_csv("tmp/bench_compare/summary.csv")
    stats = df[df["solver"] == "sa"]["operators_stats"].iloc[0]
    print(stats)
    PY

.. _heuristic-objective-weights:

Objective Weights, Automatic Overrides, and Hard Violations
-----------------------------------------------------------

SA, ILS, and Tabu maximise the heuristic objective

.. code-block:: text

    ω_prod·(delivered − leftover) − ω_mob·mobilisation − ω_trans·transitions
        − ω_land·landing_surplus − P·(hard violations)

with the scenario's ``objective_weights`` unless overrides apply.

**Automatic overrides.** ``AUTO_OBJECTIVE_WEIGHT_OVERRIDES``
(``src/fhops/optimization/heuristics/common.py``) replaces the weights of two shipped reference
scenarios whenever no ``--objective-weight`` / ``objective_weight_overrides`` is given:

.. list-table::
   :header-rows: 1

   * - Scenario (``Scenario.name``)
     - Heuristic weights
     - Scenario (MILP) weights
   * - FHOPS Tiny7 (``examples/tiny7``)
     - production 1.0, mobilisation 0.2, transitions 0.1, landing_surplus 0.05 (soft landings)
     - production 1.0, mobilisation 0.5, transitions 0.0, landing_surplus 0.0 (hard landings)
   * - FHOPS Small21 (``examples/small21``)
     - production 1.0, mobilisation 0.2, transitions 0.1, landing_surplus 0.05 (soft landings)
     - production 1.0, mobilisation 0.5, transitions 0.0, landing_surplus 0.0 (hard landings)

They date from the heuristic tuning work on these one-machine-per-landing scenarios (a lower
mobilisation weight and soft landings let the search move machines between landings), and the
published Tiny7/Small21 heuristic results use them. A heuristic objective for these scenarios is
therefore **not** on the operational MILP's scale. Since 1.0.1 (#140) the overrides are reported
wherever they apply:

* ``fhops solve-heur`` / ``solve-ils`` / ``solve-tabu``, ``fhops benchmark`` and ``fhops bench suite``
  print a one-line ``Note: Heuristic objective uses built-in weight overrides ...``;
* the solver ``meta`` carries ``objective_weight_overrides``, ``objective_weight_overrides_source``
  (``auto`` or ``explicit``) and ``scenario_objective_weights``; telemetry ``config`` records the
  overrides and their source;
* ``fhops benchmark`` prints ``SA obj (override weights)`` and ``SA obj (scenario weights)`` next to
  ``MIP obj``, and ``fhops bench suite`` adds the ``objective_weights_source``,
  ``objective_weight_overrides``, ``objective_scenario_weights`` and
  ``objective_scenario_weights_vs_mip_gap`` summary columns (see :doc:`benchmarks`).

To compare plans from different sources under one set of weights, score the assignment tables with
``fhops.optimization.heuristics.common.evaluate_assignments(pb, assignments, ctx=None)``: it scores
a table as planned (no repair; rows breaking hard rules are penalised), uses a ``production`` column
when present (operational-MILP plans: planned production and idle locked slots, as playback does),
and uses the scenario's own weights unless you pass a context with overrides. For a heuristic export
scored with the solver's weights it returns the solver's ``objective``.

**Hard violations.** Each assignment that is unavailable or blacked out, breaks a lock, uses a
forbidden role, falls outside the block window, has no production rate, breaks sequencing, or
overloads a landing while ``landing_surplus`` is weighted 0 costs

.. code-block:: text

    P = max(1000, 2·ω_prod·r_max + ω_mob·c_max + 1)

where ``r_max`` is the largest production rate (m³/shift) and ``c_max`` the largest cost of one
machine move. ``P`` strictly exceeds what one assignment can add to the objective through its own
production (delivered and no longer counted as leftover) and mobilisation, so a plan never gains by
keeping a violating assignment for its direct contribution. Before #140 ``P`` was a flat 1000, which
a machine-shift worth more than 1000 could outweigh (an SA plan overloading a hard landing then
beat the MILP's hard optimum). Indirect effects through downstream sequencing are not bounded.
Scenarios whose largest rate is below about 500 m³/shift keep ``P = 1000``.

**Landing guard.** With ``landing_surplus`` weighted 0 the heuristics' repair pass keeps or fills an
unlocked slot only when the block's landing has room in that shift, on **every** day; a landing
with capacity 0 admits no machine. Until #140 the guard ran on multi-shift days only, so every
published med42 heuristic plan overloaded single-shift landings 49–61 times (plans the MILP
forbids). With a positive ``landing_surplus`` weight (soft landings, e.g. the Tiny7/Small21
overrides) overloads remain a priced choice and the repair is unchanged.

Because the repair visits the machines of a slot in harvest-system role order, a hard capacity
smaller than the crew used to go to the upstream roles first: while felling work remained anywhere
on a landing the feller took its only place, downstream roles never worked there and the plan
delivered nothing (a feller → skidder → loader chain on a capacity-1 landing: SA 0 m³, MILP
500 m³). Since #140, before repairing a slot the repair predicts the block each unlocked downstream
machine whose input is already staged would take, and that machine's landing place is held against
machines of earlier roles ("pull" allocation: staged volume is moved on before more is produced).
The same chain now delivers 500 m³ (the MILP optimum), with no landing overloads and no sequencing
violations. The prediction depends only on the state at the start of the slot, so the repair stays
idempotent and the reported objective remains a fresh evaluation of the plan. The reservation is a
heuristic, not a guarantee: a plan can still deliver less than the MILP when the reservation or a
lock sends a machine to the wrong place, but it does not create hard violations.

**Locked slots (#158).** A locked slot (``ScheduleLock``) always keeps its block, but it produces
only what its staged input allows, as in the operational MILP (constraint E13 fixes the assignment,
not the production) and in playback: a downstream role locked to a slot with no staged upstream
volume, or below its head-start or truckload threshold, simply idles, and a slot with some input
produces that much. ``ScheduleLock.production``, when set, caps the slot's production (``0`` keeps
it idle; a day-level lock's value applies to each of its slots); the heuristics, the evaluator and
playback of a table without a ``production`` column use the same rule
(``SequencingTracker.process(..., locked=True)``). Before #158 the heuristics proposed the full rate
for every locked slot and charged a hard violation when the input was missing, so an unlocked
downstream machine that the repair sent to the block earlier (for example through the landing
reservation above) could make a later locked slot a violation: a feller → skidder → loader chain
with the skidder locked on day 3 scored −2200 (two violations) instead of the MILP's −200. Locks
only cause hard violations now when they contradict a hard rule themselves (for example more
locked machines on a landing than its hard capacity; the MILP plan pays the same penalty).

**Blocks the fleet cannot work (#158).** A block whose harvest system has none of its roles in the
fleet admits no machine (``OperationalProblem.allowed_roles`` is an empty set): the heuristics, the
sanitizer and the MILP leave it unworked and its volume counts as leftover. Before #158 such a block
had no role restriction, so any machine could work it and playback credited production that no
terminal role ever delivered. ``fhops validate`` prints a warning for these blocks, and for blocks
whose system's terminal role (e.g. the loader) has no machine.

Next Steps
----------

* Use the :doc:`benchmarks` how-to to interpret comparison metrics and plots.
* See ``notes/metaheuristic_hyperparam_tuning.md`` for the long-term tuning roadmap.
* When presets change, rerun ``fhops bench suite`` and regenerate plots with ``scripts/render_benchmark_plots.py`` before updating documentation.
* For CLI flag details, refer back to :doc:`../reference/cli`.
