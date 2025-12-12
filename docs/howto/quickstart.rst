Quickstart
==========

The quickest way to explore FHOPS is with the bundled ``examples/tiny7`` scenario.

Bootstrap Environment
---------------------

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]

Workbench: ``examples/tiny7``
--------------------------------

.. code-block:: bash

   fhops validate examples/tiny7/scenario.yaml
   fhops solve-mip examples/tiny7/scenario.yaml --out examples/tiny7/out/mip_solution.csv
   fhops solve-heur examples/tiny7/scenario.yaml --out examples/tiny7/out/sa_solution.csv
   fhops evaluate examples/tiny7/scenario.yaml examples/tiny7/out/mip_solution.csv

What those commands do:

- ``fhops validate`` ensures CSV/YAML inputs satisfy the data contract.
- ``fhops solve-mip`` builds a Pyomo model and solves it with HiGHS. The resulting CSV
  lists the selected machine/block assignments.
- ``fhops solve-heur`` runs the simulated annealing heuristic.
- ``fhops evaluate`` replays a schedule CSV and reports KPIs such as production,
  mobilisation cost, and sequencing health (when harvest systems are configured).

Objective weights live alongside the scenario metadata (`objective_weights` block in YAML).
Use them to balance production against mobilisation spend, transition counts, or landing slack
penalties before re-running the solvers.

Regression Fixture (Phase 1 Baseline)
-------------------------------------

The repository ships a deterministic scenario that exercises mobilisation penalties,
machine blackouts, and harvest-system sequencing:
``tests/fixtures/regression/regression.yaml``. The companion ``baseline.yaml`` file stores
expected KPI/objective values the automated tests assert against.

.. code-block:: bash

   fhops solve-mip tests/fixtures/regression/regression.yaml --out /tmp/regression_mip.csv
   fhops solve-heur tests/fixtures/regression/regression.yaml --out /tmp/regression_sa.csv
   fhops evaluate tests/fixtures/regression/regression.yaml /tmp/regression_sa.csv

The regression baseline encodes these expected values:

.. list-table::
   :header-rows: 1

   * - Metric
     - Expected
   * - SA objective (seed 123, 2 000 iters)
     - ``2.0``
   * - Total production
     - ``8.0``
   * - Mobilisation cost
     - ``6.0``
   * - Sequencing violations
     - ``0`` (clean schedule)

Compare the CLI output against the table to confirm your environment matches the regression
baseline. The fixture is also useful when iterating on mobilisation or sequencing logic.

For more examples and advanced options, see the CLI reference (:doc:`../reference/cli`) and
the data contract guide (:doc:`data_contract`).

Rolling horizon loop (playback + KPIs)
--------------------------------------
Use the rolling planner to generate a locked plan, then compare it to a monolithic baseline. Tiny7
runs quickly with either SA or HiGHS; swap in med42 when you want a realistic ladder example.

.. code-block:: bash

   # 1) Full-horizon baseline (HiGHS)
   fhops solve-mip examples/tiny7/scenario.yaml --out tmp/tiny7_full.csv --driver highs

   # 2) Rolling MILP (Gurobi shown; use --mip-solver highs if Gurobi is unavailable)
   fhops plan rolling examples/tiny7/scenario.yaml \
     --master-days 7 --sub-days 7 --lock-days 7 \
     --solver mip --mip-solver gurobi --mip-solver-option Threads=8 \
     --out-assignments tmp/tiny7_rolling.csv --out-json tmp/tiny7_rolling.json

   # 3) Evaluate KPI deltas in Python
   python - <<'PY'
   import pandas as pd
   from fhops.planning import comparison_dataframe, compute_rolling_kpis
   from fhops.scenario.io import load_scenario

   scenario = load_scenario("examples/tiny7/scenario.yaml")
   baseline = pd.read_csv("tmp/tiny7_full.csv")
   rolling_df = pd.read_csv("tmp/tiny7_rolling.csv")

   comparison = compute_rolling_kpis(
       scenario,
       rolling_df,  # assignments exported from fhops plan rolling
       baseline_assignments=baseline,
   )
   plot_df = comparison_dataframe(
       comparison,
       metrics=["total_production", "mobilisation_cost"],
   )
   print(plot_df[["metric", "delta", "pct_delta"]])
   PY

Use ``fhops eval playback ... --assignments tmp/tiny7_rolling.csv`` when you want KPI totals without
running Python. For richer plots and FAQ, see :doc:`rolling_horizon`.

Shift-enabled scenarios
-----------------------
When your scenario defines shifts/blackouts (see :doc:`data_contract`), include ``shift_id`` in
schedule CSVs and use the playback CLI to validate both shift-level and day-level KPIs:

.. code-block:: bash

   # Example snippet inside your scenario YAML
   # timeline:
   #   horizon_days: 10
   #   shifts:
   #     - id: D
   #       label: Day
   #     - id: N
   #       label: Night
   #   shifts_per_day: 2
   # data:
   #   shift_calendar: data/shift_calendar.csv  # columns: machine_id,day,shift_id,available

   fhops validate my_shift_scenario.yaml

   fhops solve-mip-operational my_shift_scenario.yaml \
     --out tmp/shift_assignments.csv --time-limit 120

   fhops eval playback --scenario my_shift_scenario.yaml \
     --assignments tmp/shift_assignments.csv \
     --shift-out tmp/shift_summary.csv \
     --day-out tmp/day_summary.csv \
     --shift-parquet tmp/shift.parquet \
     --day-parquet tmp/day.parquet

Inspect ``shift_summary.csv`` vs. ``day_summary.csv`` to confirm totals roll up as expected and that
blackout days/shifts are honoured. Use the Parquet outputs for downstream notebooks or dashboards.
