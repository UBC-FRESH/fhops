``fhops.planning`` Package
==========================

Rolling-horizon replanning utilities that are shared between the CLI and Python callers. Use these
helpers to generate iteration plans, slice scenarios into sub-horizons, and execute rolling solves
with either the simulated annealing or MILP hooks.

Typical usage:

.. code-block:: python

   from fhops.planning import (
       comparison_dataframe,
       compute_rolling_kpis,
       evaluate_rolling_plan,
       solve_rolling_plan,
   )
   from fhops.scenario.io import load_scenario
   import pandas as pd

   scenario = load_scenario("examples/tiny7/scenario.yaml")
   result = solve_rolling_plan(
       scenario,
       master_days=14,
       subproblem_days=7,
       lock_days=7,
       solver="sa",
       sa_iters=200,
       sa_seed=123,
   )
   print(result.metadata, len(result.locked_assignments))

   baseline_df = pd.read_csv("tmp/tiny7_full_horizon.csv")
   comparison = compute_rolling_kpis(
       scenario,
       result,
       baseline_assignments=baseline_df,
   )
   print(comparison.delta_totals.get("total_production_delta"))

   # Or use the reporting wrapper that preserves extra metadata and deltas.
   comparison = evaluate_rolling_plan(
       result,
       scenario,
       baseline_assignments=baseline_df,
       baseline_label="full_sa",
   )
   print(comparison.deltas.get("total_production_delta"))

   # Build a plotting-friendly frame for MASc experiments.
   plot_df = comparison_dataframe(comparison, metrics=["total_production", "mobilisation_cost"])

Solver options (MILP)
---------------------

Pass solver-specific options (threads, gap targets, log files) via ``mip_solver_options`` on the
library helper, or set environment variables for backends like Gurobi:

.. code-block:: python

   result = solve_rolling_plan(
       scenario,
       master_days=42,
       subproblem_days=21,
       lock_days=7,
       solver="mip",
       mip_solver="gurobi",
       mip_time_limit=600,
       mip_solver_options={"Threads": 64, "LogFile": "med42.log"},
   )

``mip_solver_options`` is also accepted by :func:`fhops.planning.get_solver_hook` for direct hook
construction.

Assignments exported by ``fhops plan rolling`` (``--out-assignments``) can be fed directly into
:func:`fhops.planning.compute_rolling_kpis` alongside a monolithic baseline DataFrame when you want
KPI deltas without re-running the solver in Python.

.. automodule:: fhops.planning
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:
