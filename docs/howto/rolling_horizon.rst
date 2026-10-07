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
   assignment proposes its planned production when the lock carries one (MILP runs store the MILP
   ``prod`` value in ``ScheduleLock.production``) and ``min(rate, block remaining)`` otherwise (SA
   runs, user locks); the tracker caps it by the role's remaining output and the staged upstream
   inventory (output becomes available downstream from the next shift slot). The carried state is
   exactly what :func:`fhops.planning.compute_rolling_kpis` reports for the same plan, and for MILP
   runs it is the state the window MILP planned, so stitched MILP plans replay without sequencing
   violations. A lock without ``shift_id`` (day-level lock, e.g. from a custom solver hook) is
   replayed in every shift slot of its day in which the machine is available, which is how the
   operational MILP and the heuristics apply it (since 1.0.1, #125); a day-level lock that carries a
   planned ``production`` on a day with several such slots is rejected (``ValueError``), because the
   split of that volume over the shifts is ambiguous. The stitched plan stores such locks expanded
   to one lock per shift slot.
2. **Derive the window's boundary state** from the tracker at the end of the last locked day:

   - ``Block.work_required`` = remaining terminal volume (finished blocks stay in the window with
     ``work_required = 0``, so their ids remain valid);
   - ``Scenario.initial_state`` (see :ref:`initial-state`): per explicit-system block,
     ``role_remaining``, ``staged_inventory`` (non-terminal roles) and ``role_shift_counts``; per
     machine, ``last_block_id`` = the block of its last locked assignment in chronological slot
     order (day, then the scenario's shift order). Entries at their contract default (zero, or ``role_remaining`` equal to
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

Per-iteration telemetry (:class:`fhops.planning.RollingIterationSummary`, the ``iterations``
records of :func:`fhops.planning.summarize_plan` and the CLI exports) reports:

- ``iteration_index``, ``start_day``, ``horizon_days``, ``lock_days``, ``locked_assignments``;
- ``remaining_work_start`` — terminal m³ still to deliver across all base blocks at the window start;
- ``status`` — ``solved``, ``no_solution`` or ``skipped`` (see :ref:`rolling-no-plan`), and
  ``has_solution`` (``False`` only for ``no_solution``);
- ``planned_delivered`` — m³ the window's whole plan delivers when replayed on the window scenario;
- ``locked_delivered`` — m³ the locked span delivers in the stitched-plan replay (these add up to the
  stitched plan's ``total_production``);
- ``locked_production`` — machine m³ (every role) the window plan produces in its lock span (window
  replay);
- ``empty`` — the window's blocks still held work but its lock span produces nothing (no locks, or
  only locks without production) or its plan delivers nothing;
- ``error`` — the solver failure text of a ``no_solution`` window whose solver failed (e.g. an
  unknown or unlicensed solver), else ``null``;
- ``objective`` (the base objective; see :ref:`rolling-earliness`), the hook's wall-clock
  ``runtime_s``, and ``warnings`` (solver status and termination condition, the MILP earliness
  stage ``earliness=<status> value=<E> …``, plus the no-solution / skipped / empty-window notices).

The run summary adds ``empty_windows``, ``no_solution_windows`` and ``skipped_windows`` counts and the
``empty_window_indices`` / ``no_solution_window_indices`` lists.

.. _rolling-earliness:

MILP windows: earliness tie-break
---------------------------------
The operational MILP objective rewards delivered volume and charges leftovers, landing surplus and
moves; it does not depend on *when* inside the window the work is done. Many window plans are
therefore tied, and the solver may return one that does the work at the end of the window. Only the
lock span is kept, so such a window locks idle days and the next window defers again. In the FHOPS
1.0.1 audit (#141), one machine with 300 m³ at 100 m³/day (``master/sub/lock = 10/6/1``) worked days
8–10 instead of 1–3. On the Jaffray ``ka_6`` scenario (``112/14/7``, HiGHS, 120 s windows), windows
7–14 locked no production while work remained.

Since 1.0.1 the MILP hook (:class:`fhops.planning.MILPSolver`) breaks these ties lexicographically
(``earliness=True``, default):

1. Solve the window's base objective (stage 1, value ``z1``).
2. Re-solve with the production-weighted earliness ``E = Σ_s w_s Σ_{m,b} p[m,b,s]`` as the objective
   (``w_s`` falls linearly from 1 in the first slot to ``1/|S|`` in the last), subject to
   ``objective ≥ z1 − 10⁻⁶·max(1, |z1|)``. This solve is warm-started from the stage-1 plan.

The window's base objective is unchanged (within a relative ``10⁻⁶``, 100× tighter than HiGHS's
default MIP gap), and work moves into the lock span whenever the base objective allows it. The reported window
``objective`` is the base objective. The earliness stage is reported as an
``earliness=<status> value=<E> stage1_value=<E1> termination_condition=<…>`` warning: ``applied``,
or ``kept_stage1`` when stage 2 returned no usable solution and the stage-1 plan is kept. A single
weighted objective ``OBJ + ε·E`` is not used, because no data-independent ``ε`` can be guaranteed
safe, and an ``ε`` small enough to be safe in practice is below the solver's relative gap (see the
formulation's *Earliness tie-break* paragraph in :doc:`optimization_formulation`).

Cost: a second solve per window, limited by ``--mip-earliness-time-limit`` (default
``--mip-time-limit``), so a window can take up to twice the time limit. The stage is skipped for
windows whose lock span covers the whole window (the final window, ``sub_days == lock_days``),
where timing inside the window does not change what is locked. A single-window run therefore stays
a direct solve. Disable the stage with ``--no-mip-earliness`` (``mip_earliness=False`` in
:func:`fhops.planning.solve_rolling_plan` / :func:`fhops.planning.get_solver_hook`). Standalone
``fhops solve-mip-operational`` does not use it by default (``--earliness`` enables it), so the
published single-horizon optimum and its solve time stay unchanged.

The SA hook does not show this deferral: its construction fills the earliest available slots, and
on ``ka_6`` (``112/14/7``, ``112/7/1``, ``112/28/14``, 500 iterations) its windows never lock idle
days while work remains.

.. _rolling-no-plan:

Windows without a plan
----------------------
A window may end without a usable plan: the MILP hits its time limit before finding an incumbent,
the window is infeasible (e.g. a user lock that cannot be met inside a short window, see
`Limitations`_), or the solver fails (unknown or unlicensed solver, solver crash). FHOPS 1.0.1
(#117) applies one documented policy instead of aborting the run:

1. The iteration is recorded with ``status = "no_solution"``, ``has_solution = False``,
   ``objective = None`` and a warning (also emitted as a Python ``UserWarning`` and collected in
   ``RollingPlanResult.warnings``). The MILP hook reports solver failures (driver
   ``outcome = "error"``) as ``solver_error=<text>`` and in the iteration's ``error`` field, and keeps
   the solver status/termination condition. Exceptions raised while building the window problem or
   model are FHOPS defects or invalid data: since #141 they propagate (with the run so far attached
   as ``partial_result``) instead of being recorded as a window without a solution.
2. **No** assignments are locked for its lock span: machines are idle on those days, and user locks
   in that span are not applied either (the warning counts them).
3. The carried state is unchanged across the idle span (nothing was replayed), and the next window is
   solved from it.
4. The result keeps per-iteration status (``RollingPlanResult.no_solution_windows`` /
   ``empty_windows``, ``summarize_plan()["no_solution_windows"]``).

Windows with nothing to plan (no blocks whose time window overlaps the window, no production rates,
or no available shift slots — e.g. days not covered by a partial ``shift_calendar``) are not passed to
the solver and are recorded with ``status = "skipped"``; they are idle as well.

A **solved** window whose blocks still hold work is flagged ``empty`` with a warning if its lock span
produces nothing (no locks, or only locks without production, ``locked_production = 0``) or its
plan delivers no volume (e.g. an all-zero time-limited incumbent, or a plan that defers all work past
the lock span). No-solution and skipped windows with remaining work are flagged ``empty`` too. A
lock span whose blocks only open later in the window is flagged as well. Before #141 only windows
without any lock counted, so locks that kept a machine assigned but idle hid deferred windows.

To stop instead of continuing (:func:`fhops.planning.solve_rolling_plan`,
:func:`fhops.planning.run_rolling_horizon`, CLI):

- ``fail_on_no_solution=True`` / ``--fail-on-no-solution`` stops at the first window without a
  solution;
- ``fail_on_empty_window=True`` / ``--fail-on-empty-window`` stops at the first window without a
  solution **or** solved to an empty plan (since #141; before, it stopped only at windows without a
  solution, which is now ``--fail-on-no-solution``).

Both raise :class:`fhops.planning.RollingInfeasibleError` naming the iteration, with the run so far
in ``partial_result``. Skipped windows never raise.

The CLI **always** writes the requested outputs (``--out-json``, ``--out-assignments``, iteration
JSONL/CSV). On failure they hold the assignments locked so far and the recorded iterations, and the
JSON summary gets an ``error`` field. Exit codes of ``fhops plan rolling``:

- ``0`` — the run completed and at least one window passed to the solver returned a solution;
- ``1`` — a ``--fail-on-*`` flag stopped the run, the run raised, or **no** window returned a
  solution (e.g. every window failed with a solver error; ``error`` is
  ``"no window returned a solution"``);
- ``2`` — usage error, printed without a traceback: invalid horizon arguments (``--master-days``
  ``< 1`` or beyond the scenario's ``num_days``, ``--lock-days < 1``,
  ``--sub-days < --lock-days``), ``--max-iterations < 1``, an unknown ``--solver``, or a
  ``--mip-solver`` that Pyomo reports as unavailable (e.g. a typo or a missing Gurobi install).

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

Switch to the operational MILP for each subproblem (long-running: up to ``--mip-time-limit`` seconds
per window; HiGHS typically uses the full limit on med42):

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
or environment variables such as ``GRB_THREADS`` (requires a Gurobi licence; long-running):

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
- JSON summary (``--out-json``) with the iteration records (see the telemetry fields above),
  ``total_locked_assignments``, the empty/no-solution/skipped window counts, warnings, metadata
  (scenario, horizons, solver, MILP backend, ``mip_earliness``, ``fail_on_empty_window``,
  ``fail_on_no_solution``), and ``error`` when the run failed part-way or no window returned a
  solution.
- CSV of locked assignments (``--out-assignments``) aggregated across all iterations. Columns:
  ``machine_id``, ``block_id``, ``day`` (base-scenario day), ``shift_id``, ``assigned`` (always
  ``1``), ``production`` (MILP runs only: the window MILP's planned m³ for that slot, which playback
  and :func:`fhops.planning.compute_rolling_kpis` replay instead of the full rate), then the run
  metadata (``scenario``, ``solver``, ``master_days``, ``subproblem_days``, ``lock_days``,
  ``start_day``). The file drops directly into playback or KPI tooling. ``shift_id`` keeps
  multi-shift plans unambiguous (one row per machine and shift slot); keep it when post-processing,
  because playback needs it to place multi-shift assignments.
- Optional per-iteration exports: JSONL (``--out-iterations-jsonl``) and CSV
  (``--out-iterations-csv``) with one record per iteration (same fields as the JSON ``iterations``).

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
sub-horizons).

.. note::

   **Window objectives are not comparable across versions.** Since 1.0.1 each window solves the
   carried remaining volume, so its objective includes the leftover (unfinished-volume) penalty on
   that carried volume. FHOPS 1.0.0 windows re-planned every block's full volume. Neither the last
   window's objective nor a sum of window objectives measures plan quality, and 1.0.1 window
   objectives cannot be compared with 1.0.0 ones. Use the stitched-plan KPIs
   (``total_production``, ``remaining_work_total``, mobilisation cost, sequencing violations)
   instead.

Use :func:`fhops.planning.rolling_assignments_dataframe` to obtain a playback-ready DataFrame and :func:`fhops.planning.compute_rolling_kpis` to compare the rolling run against a
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
DataFrame for plotting suboptimality across horizon/lock settings. It takes the result of
:func:`fhops.planning.evaluate_rolling_plan` (not the :class:`~fhops.planning.RollingKPIComparison`
returned by :func:`~fhops.planning.compute_rolling_kpis`, which has ``delta_totals`` instead).
Example skeleton:

.. code-block:: python

   import matplotlib.pyplot as plt
   import pandas as pd
   from fhops.planning import comparison_dataframe, evaluate_rolling_plan, solve_rolling_plan
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
       comparison = evaluate_rolling_plan(
           result,
           scenario,
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
   from fhops.planning import compute_rolling_kpis
   from fhops.scenario.io import load_scenario

   METRICS = ["total_production", "mobilisation_cost"]

   scenario = load_scenario("examples/med42/scenario.yaml")
   baseline = pd.read_csv("tmp/med42_baseline.csv")
   configs = {
       "21_7": pd.read_csv("tmp/med42_roll_21_7.csv"),
       "14_7": pd.read_csv("tmp/med42_roll_14_7.csv"),
   }
   frames = []
   for label, df in configs.items():
       comp = compute_rolling_kpis(scenario, df, baseline_assignments=baseline)
       deltas = comp.delta_totals or {}
       frame = pd.DataFrame(
           {
               "metric": metric,
               "rolling": comp.rolling_kpis.get(metric),
               "baseline": comp.baseline_kpis.get(metric),
               "delta": deltas.get(f"{metric}_delta"),
               "pct_delta": deltas.get(f"{metric}_pct_delta"),
           }
           for metric in METRICS
       )
       frame["config"] = label
       frames.append(frame)
   plot_df = pd.concat(frames, ignore_index=True)
   plot_df.to_csv("docs/assets/rolling/masc_comparison_med42.csv", index=False)
   # render your preferred plot (matplotlib/seaborn/altair) and save alongside the CSV

Gotchas
-------
- Ensure ``master_days + start_day - 1 <= Scenario.num_days``; otherwise the CLI fails fast with a
  usage error (exit code 2).
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
- Locked assignments are treated as immutable across iterations. A window without a solution or with
  nothing to plan leaves its lock span idle and the run continues (see :ref:`rolling-no-plan`);
  use ``--fail-on-no-solution`` or ``--fail-on-empty-window`` to stop instead.
- The hooks enforce locks as hard constraints (equality constraints in the operational MILP, the
  lock-aware sanitizer in SA); they do not pass incumbents or warm starts to the solver.
- Telemetry/reporting layers will evolve; current exports are meant to unblock experimentation.
- ``master_days`` must not exceed the base scenario horizon. Use a scenario with enough days or lower
  the master/sub/lock settings to fit within ``Scenario.num_days``.
- ``--mip-solver`` passes through to Pyomo (use ``highs`` or ``gurobi``; ``auto`` resolves to
  ``highs``); ``--max-iterations N`` (``N >= 1``) caps the rolling loop for smoke tests or partial
  plans.
- User locks outside their block's ``earliest_start``/``latest_finish`` window are rejected up front
  with :class:`fhops.planning.RollingInfeasibleError` (before any window is solved), whatever the
  master/sub/lock settings; scenario validation rejects them at load time as well (#118). Valid locks
  always fall in a window that keeps their block. Conflicting locks are rejected by scenario
  validation.

Limitations
-----------
- **No end-of-window valuation.** Window objectives reward only terminal (delivered) volume, so a
  window shorter than the harvest-system pipeline can see no value in upstream work: e.g. on tiny7
  (four-role chain) a MILP run with ``master/sub/lock = 7/3/1`` plans no felling at all. Since MILP
  locks replay their planned production (1.0.1, #109), the window MILP's choice of how much
  upstream work to do on locked days (any amount its own window cannot finish has no value, so
  equal-objective plans are broken arbitrarily by the solver) carries into the next window: tiny7
  ``7/4/2`` and ``7/5/3`` deliver about 3.9 of 4.4 thousand m³ (the earlier rate-based replay
  credited unplanned full-rate upstream work and reported the full volume, together with
  sequencing violations), ``7/6/3`` about 4.40 and ``7/7/7`` the full volume. Choose ``sub_days``
  comfortably longer than the number of roles plus ``lock_days``. Without a terminal value, short
  windows can also make **user locks on downstream roles** infeasible: e.g. a skidder locked on the
  first day of a two-day window that cannot fell (and stage) the wood it needs before that shift. Such
  a window MILP has no solution and is handled by the no-solution policy (idle lock span, warning,
  ``status = "no_solution"``) rather than aborting the run; SA treats locks as fixed and replays them
  without the missing input. Lengthen ``sub_days`` or overlap windows (``sub_days > lock_days``) when
  this happens.
- **Replay rule vs. MILP plan.** Resolved in 1.0.1 (#109): playback, the heuristics, and the MILP
  share one sequencing semantics (staged output usable from the next shift slot, head-start buffers
  as staged volume, per-role output capped by the block volume), and MILP rolling locks carry the
  planned production, so stitched MILP plans replay without sequencing violations and the carried
  state is the state the window MILP planned.
- **Blocks outside a window** are dropped from that window. If a machine's carried
  ``last_block_id`` is such a block (its ``latest_finish`` has passed), the position is dropped
  for that window with a warning in ``RollingPlanResult.warnings`` and its next move is not
  charged in the window solve (playback still charges it).
- **Partial shift calendars.** Resolved in 1.0.1 (#117): when the base scenario has a
  ``shift_calendar``, days without entries have no shift slots in every window too (a window entirely
  outside the calendar is skipped), so rolling runs no longer invent ``S1`` capacity there.
- **Blackouts in the MILP.** Resolved in 1.0.1 (#110): rebased blackouts are honoured by the
  operational MILP (zero availability in the blocked slots) as well as by the heuristics, and
  flagged by playback.
