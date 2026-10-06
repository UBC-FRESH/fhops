Rolling-Horizon Planning
========================

FHOPS can build multi-week plans by solving shorter subproblems and locking in the leading days
before advancing the horizon. This page outlines the workflow and CLI surface that currently ships
with stub, SA, and MILP solver hooks, what state is carried from one window to the next, and how to
evaluate the stitched plan.

.. note::

   FHOPS 1.0.0 carried **no** state between windows: every window re-planned each block's full
   ``work_required`` (including blocks already finished in locked days), staged inventory and
   machine positions reset to zero, user locks were dropped, and blackouts were not rebased. The
   stitched plans it produced therefore under-delivered badly when evaluated against the base
   scenario. FHOPS 1.0.1 fixes this (issue #92); results produced with 1.0.0 rolling runs should be
   regenerated.

When to use
-----------
- Need a 12–16 week plan but only want to solve tractable 2–4 week subproblems.
- Desire a “locked” near-term schedule for contractors while keeping a rolling buffer for course
  corrections.
- Willing to accept some suboptimality vs. a monolithic solve in exchange for scalability.

Key parameters
--------------
- ``master_days``: total length of the plan you want to lock (e.g., 84 or 112).
- ``sub_days``: length of each optimisation window (must be >= ``lock_days``).
- ``lock_days``: number of leading days to freeze after each solve before advancing.
- Horizons must fit the scenario: ``start_day + master_days - 1 <= Scenario.num_days``. Adjust the
  values or pick a longer scenario if you hit this guardrail.

How state carries between windows
---------------------------------
Each iteration solves a window ``[start, start + sub_days - 1]`` and freezes its first
``lock_days`` days. Before the next window is solved, the orchestrator
(:func:`fhops.planning.run_rolling_horizon`) does the following:

1. **Replay the stitched locked plan** (all locks so far, base-day coordinates, ``shift_id``
   preserved) against the **base** scenario with the deterministic playback sequencing tracker
   (:func:`fhops.planning.carry_forward_state`). Production follows the playback rule: each locked
   assignment proposes ``min(rate, block remaining)`` and the tracker caps it by the role's
   remaining output and the staged upstream inventory (output becomes available downstream from the
   next day). Solver-planned production (MILP ``prod`` values) is not used, so the carried state is
   exactly what :func:`fhops.planning.compute_rolling_kpis` reports for the same plan.
2. **Derive the window's boundary state** from the tracker at the end of the last locked day:

   - ``Block.work_required`` = remaining terminal volume (finished blocks stay in the window with
     ``work_required = 0``, so their ids remain valid);
   - ``Scenario.initial_state`` (see :ref:`initial-state`): per explicit-system block,
     ``role_remaining``, ``staged_inventory`` (non-terminal roles) and ``role_shift_counts``; per
     machine, ``last_block_id`` = the block of its last locked assignment ordered by
     ``(day, shift_id)``. Entries at their contract default (zero, or ``role_remaining`` equal to
     the remaining volume) are omitted.
3. **Slice the base scenario** for the window: machine and shift calendars, timeline blackouts
   (clipped to the window and shifted so the window start is day 1), block windows, production
   rates, and mobilisation distances are rebased; blocks whose ``earliest_start``/``latest_finish``
   window does not overlap the sub-horizon are dropped.
4. **Merge user locks**: ``Scenario.locked_assignments`` entries that fall inside the window are
   rebased (``shift_id`` kept) and attached to the window scenario; the solver hooks merge the locks
   they receive with the scenario's own locks instead of overwriting them, so user locks are
   enforced in every window that covers them and end up in the stitched plan.

If the base scenario already has an ``initial_state``, the first window uses it verbatim and the
replay for later windows starts from it, so user-supplied state and the stitched plan compose. The
first window otherwise equals the base scenario restricted to ``sub_days``; a single-window run
(``master_days = sub_days = lock_days``) is identical to a direct solve.

Per-iteration telemetry reports ``remaining_work_start`` (terminal m³ still to deliver at the window
start), the hook's wall-clock ``runtime_s``, objective, and solver status.

CLI usage
---------
Run the rolling planner with either the heuristic or MILP backend:

.. code-block:: bash

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 42 \
     --sub-days 21 \
     --lock-days 7 \
     --solver sa \
     --sa-iters 500 \
     --sa-seed 42 \
     --out-json tmp/med42_rolling.json \
     --out-assignments tmp/med42_rolling_assignments.csv

Switch to the operational MILP for each subproblem:

.. code-block:: bash

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 42 \
     --sub-days 21 \
     --lock-days 7 \
     --solver mip \
     --mip-solver highs \
     --mip-time-limit 300 \
     --out-json tmp/med42_mip_rolling.json

Pass solver-specific options directly to the MILP backend using ``--mip-solver-option`` (repeatable)
or environment variables such as ``GRB_THREADS``:

.. code-block:: bash

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 42 --sub-days 21 --lock-days 7 \
     --solver mip --mip-solver gurobi \
     --mip-solver-option Threads=64 --mip-time-limit 600 \
     --out-json tmp/med42_gurobi.json --out-assignments tmp/med42_gurobi_assignments.csv

Worked example (tiny7)
----------------------
The tiny7 scenario is short enough to demonstrate the wiring quickly:

.. code-block:: bash

   fhops plan rolling examples/tiny7/scenario.yaml \
     --master-days 7 --sub-days 7 --lock-days 7 \
     --solver sa --sa-iters 200 --sa-seed 99 \
     --out-json tmp/tiny7_rolling.json \
     --out-assignments tmp/tiny7_rolling_assignments.csv \
     --out-iterations-jsonl tmp/tiny7_iterations.jsonl \
     --out-iterations-csv tmp/tiny7_iterations.csv

Check the JSON/CSV outputs to see iteration windows and the locked assignments; swap ``--solver
mip`` and set ``--mip-solver highs`` for a small MILP-backed run.

Outputs
-------
- JSON summary (``--out-json``) with iteration windows, locked counts, objectives, runtimes,
  warnings, and metadata (scenario, horizons, solver).
- CSV of locked assignments (``--out-assignments``) aggregated across all iterations. Columns
  include ``machine_id``, ``block_id``, ``day``, ``shift_id``, ``assigned``, and run metadata
  (scenario, solver, master/sub/lock spans, start day) so the file can drop directly into playback
  or KPI tooling. ``shift_id`` keeps multi-shift plans unambiguous (one row per machine and shift
  slot).
- Optional per-iteration exports: JSONL (``--out-iterations-jsonl``) and CSV
  (``--out-iterations-csv``) containing objective, runtime, lock span, ``remaining_work_start`` and
  warnings per iteration.

MILP example with solver options
--------------------------------
Use Gurobi for subproblems and pass solver options (threads, time limits) through the rolling
planner:

.. code-block:: bash

   GRB_THREADS=32 fhops plan rolling examples/med42/scenario.yaml \
     --master-days 42 --sub-days 21 --lock-days 7 \
     --solver mip --mip-solver gurobi --mip-time-limit 600 \
     --out-json tmp/med42_gurobi_rolling.json \
     --out-assignments tmp/med42_gurobi_rolling_assignments.csv

For programmatic control, pass ``mip_solver_options`` to :func:`fhops.planning.solve_rolling_plan`
or :func:`fhops.planning.get_solver_hook` (e.g., ``{\"Threads\": 64, \"LogFile\": \"med42.log\"}``).
HiGHS also honours ``mip_solver_options`` (e.g., ``{\"mip_rel_gap\": 0.01}``).

Evaluating rolling plans
------------------------
Always score a rolling run on its **stitched** locked plan replayed against the base scenario, not on
the objective of individual windows (window objectives cover overlapping, partly discarded
sub-horizons). Use :func:`fhops.planning.rolling_assignments_dataframe` to obtain a playback-ready
DataFrame and :func:`fhops.planning.compute_rolling_kpis` to compare the rolling run against a
monolithic baseline (``master_days = sub_days = lock_days``). The stitched-plan KPIs are computed with
the same playback rule as the carried state, so ``total_production`` never exceeds the base volume
and ``remaining_work_total`` equals the remaining volume the next window would have received:

.. code-block:: python

   import pandas as pd
   from fhops.planning import compute_rolling_kpis, solve_rolling_plan
   from fhops.scenario.io import load_scenario

   scenario = load_scenario("examples/med42/scenario.yaml")
   rolling = solve_rolling_plan(
       scenario,
       master_days=42,
       subproblem_days=21,
       lock_days=7,
       solver="mip",
       mip_solver="highs",
       mip_time_limit=600,
   )
   baseline_df = pd.read_csv("tmp/med42_monolithic_assignments.csv")
   comparison = compute_rolling_kpis(
       scenario,
       rolling,
       baseline_assignments=baseline_df,
   )
   print(comparison.delta_totals.get("total_production_delta"))

The ``comparison`` payload includes:

- ``rolling_assignments`` — DataFrame matching the CLI export schema (``machine_id``, ``block_id``,
  ``day``, ``shift_id``, ``assigned`` plus optional metadata when requested).
- ``rolling_kpis`` — KPI totals computed via deterministic playback.
- ``baseline_kpis`` — KPI totals for the supplied baseline DataFrame (``None`` when omitted).
- ``delta_totals`` — numeric differences keyed by ``<metric>_delta`` and percentage deltas when the
  baseline metric is non-zero.

For quick CLI-to-evaluation loops, feed ``--out-assignments`` directly into ``fhops eval-playback``
or stash the JSON summary and KPI deltas alongside telemetry artefacts for later reporting.

.. _rolling-empty-plans:

Empty rolling plans and baselines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A failed solve must never look like a perfect plan (`#108
<https://github.com/UBC-FRESH/fhops/issues/108>`_):

- An empty **rolling** plan (no locked assignments, an empty DataFrame, or an empty lock list) makes
  :func:`fhops.planning.compute_rolling_kpis` and :func:`fhops.planning.evaluate_rolling_plan` raise
  ``ValueError`` (unchanged from v1.0.0). To score it as a zero-delivery plan, call
  :func:`fhops.evaluation.compute_kpis` with an empty frame.
- An explicitly supplied but empty **baseline** (e.g. a full-horizon MILP that found no solution) is
  scored as a zero-delivery plan: ``baseline_kpis["total_production"] == 0``,
  ``remaining_work_total`` equals the scenario volume, and ``<metric>_pct_delta`` entries are omitted
  where the baseline is zero. FHOPS 1.0.0 silently dropped an empty baseline
  (``baseline_kpis=None``); passing ``baseline_assignments=None`` still skips the comparison.
- Rows with ``assigned = 0`` deliver nothing, so a frame whose rows are all unassigned is scored as a
  zero-delivery plan.

Rolling comparison helper
-------------------------
The :func:`fhops.planning.evaluate_rolling_plan` helper runs deterministic playback on the
locked assignments and compares them against a full-horizon baseline (single MILP/SA run). This
keeps MASc experiments reproducible without wiring ad-hoc notebooks.

.. code-block:: python

   import pandas as pd
   from fhops.planning import evaluate_rolling_plan, solve_rolling_plan
   from fhops.scenario.io import load_scenario

   scenario = load_scenario("examples/med42/scenario.yaml")
   rolling = solve_rolling_plan(
       scenario,
       master_days=42,
       subproblem_days=21,
       lock_days=7,
       solver="sa",
       sa_iters=400,
   )
   baseline_df = pd.read_csv("tmp/med42_full_horizon.csv")
   comparison = evaluate_rolling_plan(
       rolling,
       scenario,
       baseline_assignments=baseline_df,
       baseline_label="full_sa",
   )
   print(comparison.deltas.get("total_production_delta"))

MASc experiments & plots
------------------------
Use :func:`fhops.planning.comparison_dataframe` to gather rolling vs. baseline KPIs into a tidy
DataFrame for plotting suboptimality across horizon/lock settings. Example skeleton:

.. code-block:: python

   import matplotlib.pyplot as plt
   import pandas as pd
   from fhops.planning import comparison_dataframe, compute_rolling_kpis, solve_rolling_plan
   from fhops.scenario.io import load_scenario

   scenario = load_scenario("examples/med42/scenario.yaml")
   configs = [
       {"label": "42/21/7_sa", "master": 42, "sub": 21, "lock": 7, "solver": "sa"},
       {"label": "42/14/7_sa", "master": 42, "sub": 14, "lock": 7, "solver": "sa"},
   ]
   baseline = pd.read_csv("tmp/med42_full_horizon.csv")

   records = []
   for cfg in configs:
       result = solve_rolling_plan(
           scenario,
           master_days=cfg["master"],
           subproblem_days=cfg["sub"],
           lock_days=cfg["lock"],
           solver=cfg["solver"],
           sa_iters=400,
       )
       comparison = compute_rolling_kpis(
           scenario,
           result,
           baseline_assignments=baseline,
       )
       df = comparison_dataframe(
           comparison,
           metrics=["total_production", "mobilisation_cost"],
       )
       df["config"] = cfg["label"]
       records.append(df)

   plot_df = pd.concat(records, ignore_index=True)
   prod = plot_df[plot_df["metric"] == "total_production"]
   plt.figure(figsize=(6, 4))
   plt.bar(prod["config"], prod["pct_delta"] * 100)
   plt.ylabel("% gap vs. baseline (total production)")
   plt.title("Rolling vs. full-horizon (med42)")
   plt.tight_layout()
   plt.show()

The same DataFrame can feed seaborn/Altair plots or Markdown tables for MASc reports. Add additional
metrics (e.g., utilisation, mobilisation) to the ``metrics`` list to broaden the comparison.

Sample artefacts
----------------
Reference CSV/PNG bundles live under ``docs/assets/rolling``. They were produced with FHOPS 1.0.0,
i.e. **without** state carry-forward, and therefore overstate the rolling-horizon gap; treat them as
historical examples of the workflow and regenerate them before quoting numbers.

- ``masc_comparison_tiny7.{csv,png}`` — SA baseline (7/7/7) vs 7/5/3 and 7/4/2 (300 iters, seed 99).
- ``masc_comparison_med42.{csv,png}`` — Gurobi (Threads=64) baseline vs 21/7 and 14/7 sub/lock windows
  with short 10 s caps (solver may report "aborted with solution"; rerun with longer budgets for
  publication-ready gaps).

Artefact provenance & regeneration
----------------------------------
- Bundle size is small (~57 KB) so the artefacts ship in-repo for reproducibility.
- med42 assets used Gurobi with ``Threads=64`` and ``TimeLimit=10`` on each subproblem (baseline and
  rolling variants), seeded via the CLI flag ``--mip-solver-option``. The solver reported
  ``aborted with solution`` under the tight cap; loosen ``--mip-time-limit`` for higher-quality gaps.
- tiny7 assets used SA with 300 iterations and ``--sa-seed 99``.

To regenerate the med42 bundle locally (Gurobi licence required; the baseline is the single-window
full-horizon solve):

.. code-block:: bash

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 42 --sub-days 42 --lock-days 42 \
     --solver mip --mip-solver gurobi \
     --mip-solver-option Threads=64 --mip-time-limit 10 \
     --out-json tmp/med42_baseline.json --out-assignments tmp/med42_baseline.csv

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 42 --sub-days 21 --lock-days 7 \
     --solver mip --mip-solver gurobi \
     --mip-solver-option Threads=64 --mip-time-limit 10 \
     --out-json tmp/med42_roll_21_7.json --out-assignments tmp/med42_roll_21_7.csv

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 42 --sub-days 14 --lock-days 7 \
     --solver mip --mip-solver gurobi \
     --mip-solver-option Threads=64 --mip-time-limit 10 \
     --out-json tmp/med42_roll_14_7.json --out-assignments tmp/med42_roll_14_7.csv

Then stitch the KPI deltas and plots:

.. code-block:: python

   import pandas as pd
   from fhops.planning import comparison_dataframe, compute_rolling_kpis
   from fhops.scenario.io import load_scenario

   scenario = load_scenario("examples/med42/scenario.yaml")
   baseline = pd.read_csv("tmp/med42_baseline.csv")
   configs = {
       "21_7": pd.read_csv("tmp/med42_roll_21_7.csv"),
       "14_7": pd.read_csv("tmp/med42_roll_14_7.csv"),
   }
   frames = []
   for label, df in configs.items():
       comp = compute_rolling_kpis(scenario, df, baseline_assignments=baseline)
       frame = comparison_dataframe(comp, metrics=["total_production", "mobilisation_cost"])
       frame["config"] = label
       frames.append(frame)
   plot_df = pd.concat(frames, ignore_index=True)
   plot_df.to_csv("docs/assets/rolling/masc_comparison_med42.csv", index=False)
   # render your preferred plot (matplotlib/seaborn/altair) and save alongside the CSV

Gotchas
-------
- Ensure ``master_days + start_day - 1 <= Scenario.num_days``; otherwise the CLI fails fast.
- MILP runs can be slow—set sensible ``--mip-time-limit``/``mip_solver_options`` and use a Gurobi
  licence when available. HiGHS is the default (``--mip-solver auto`` resolves to ``highs``).
- Gurobi threads can be set via ``mip_solver_options`` (``{\"Threads\": 32}``) or ``GRB_THREADS``.
- When the solver aborts but returns a solution, treat results as heuristics; rerun with larger caps
  if you need high-quality gaps.

The comparison bundle exposes:

- ``comparison.rolling_kpis`` / ``comparison.baseline_kpis`` — KPIResult mappings with attached
  shift/day calendars.
- ``comparison.deltas`` — numeric delta/pct-delta entries (e.g., ``total_production_delta``).
- ``comparison.metadata`` — merges rolling metadata with counts of rolling/baseline assignments and
  the ``baseline_label`` string so telemetry exports retain traceability.

To feed the locked assignments into playback manually, use
:func:`fhops.planning.rolling_assignments_dataframe` to obtain a Pandas DataFrame compatible with
``fhops eval-playback`` or :func:`fhops.evaluation.run_playback`.

Notes
-----
- Locked assignments are treated as immutable across iterations; if a subproblem has no feasible
  availability, the CLI will fail fast with a clear error.
- The hooks enforce locks as hard constraints (equality constraints in the operational MILP, the
  lock-aware sanitizer in SA); they do not pass incumbents or warm starts to the solver.
- Telemetry/reporting layers will evolve; current exports are meant to unblock experimentation.
- ``master_days`` must not exceed the base scenario horizon. Use a scenario with enough days or lower
  the master/sub/lock settings to fit within ``Scenario.num_days``.
- ``--mip-solver`` passes through to Pyomo (use ``highs`` or ``gurobi``; ``auto`` resolves to
  ``highs``); ``--max-iterations`` can cap the rolling loop for smoke tests or partial plans.
- A user lock that falls in a window but targets a block outside that window's block set (its
  ``earliest_start``/``latest_finish`` window does not overlap) raises
  :class:`fhops.planning.RollingInfeasibleError`; conflicting locks are rejected by scenario
  validation.

Limitations
-----------
- **No end-of-window valuation.** Window objectives reward only terminal (delivered) volume, so a
  window shorter than the harvest-system pipeline can see no value in upstream work: e.g. on tiny7
  (four-role chain) a MILP run with ``master/sub/lock = 7/3/1`` plans no felling at all, while
  ``7/4/2`` delivers the same volume as the full-horizon solve. Choose ``sub_days`` comfortably longer than
  the number of roles plus ``lock_days``.
- **Replay rule vs. MILP plan.** The carried state follows deterministic playback (rate-based
  production, staged output usable from the next day). The operational MILP lets a downstream role
  use output from the previous *shift* of the same day, so playback can report sequencing
  violations for multi-shift MILP plans (rolling or full-horizon alike) and carries the state that
  playback, not the MILP, says was reached.
- **Blocks outside a window** are dropped from that window. If a machine's carried
  ``last_block_id`` is such a block (its ``latest_finish`` has passed), the position is dropped
  for that window with a warning in ``RollingPlanResult.warnings`` and its next move is not
  charged in the window solve (playback still charges it).
- **Blackouts in the MILP.** Rebased blackouts are honoured by the heuristics and flagged by
  playback; the operational MILP does not model ``timeline.blackouts`` (use calendars to remove
  availability if the MILP must respect them).
