Rolling-Horizon Planning
========================

FHOPS can build multi-week plans by solving shorter subproblems and locking in the leading days
before advancing the horizon. This page outlines the workflow and CLI surface that currently ships
with stub, SA, and MILP solver hooks.

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
  include ``machine_id``, ``block_id``, ``day``, ``assigned``, and run metadata
  (scenario, solver, master/sub/lock spans, start day) so the file can drop directly into playback
  or KPI tooling.
- Optional per-iteration exports: JSONL (``--out-iterations-jsonl``) and CSV
  (``--out-iterations-csv``) containing objective/runtime/lock span and warnings per iteration.

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
Use :func:`fhops.planning.rolling_assignments_dataframe` to obtain a playback-ready DataFrame and
:func:`fhops.planning.compute_rolling_kpis` to compare the rolling run against a monolithic baseline:

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
  ``day``, ``assigned`` plus optional metadata when requested).
- ``rolling_kpis`` — KPI totals computed via deterministic playback.
- ``baseline_kpis`` — KPI totals for the supplied baseline DataFrame (``None`` when omitted).
- ``delta_totals`` — numeric differences keyed by ``<metric>_delta`` and percentage deltas when the
  baseline metric is non-zero.

For quick CLI-to-evaluation loops, feed ``--out-assignments`` directly into ``fhops eval playback``
or stash the JSON summary and KPI deltas alongside telemetry artefacts for later reporting.

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
Reference CSV/PNG bundles live under ``docs/assets/rolling``:

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

To regenerate the med42 bundle locally (Gurobi licence required):

.. code-block:: bash

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 42 --sub-days 21 --lock-days 7 \
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
  licence when available. HiGHS remains the default for lightweight runs.
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
``fhops eval playback`` or :func:`fhops.evaluation.run_playback`.

Notes
-----
- Locked assignments are treated as immutable across iterations; if a subproblem has no feasible
  availability, the CLI will fail fast with a clear error.
- SA and MILP hooks accept the current locks as incumbents; MILP warm starts are best-effort.
- Telemetry/reporting layers will evolve; current exports are meant to unblock experimentation.
- ``master_days`` must not exceed the base scenario horizon. Use a scenario with enough days or lower
  the master/sub/lock settings to fit within ``Scenario.num_days``.
- ``--mip-solver`` passes through to Pyomo (use ``highs`` or ``gurobi``); ``--max-iterations`` can
  cap the rolling loop for smoke tests or partial plans.
