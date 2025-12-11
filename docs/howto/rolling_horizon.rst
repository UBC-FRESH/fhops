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

CLI usage
---------
Run the rolling planner with either the heuristic or MILP backend:

.. code-block:: bash

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 84 \
     --sub-days 28 \
     --lock-days 14 \
     --solver sa \
     --sa-iters 500 \
     --sa-seed 42 \
     --out-json tmp/med42_rolling.json \
     --out-assignments tmp/med42_rolling_assignments.csv

Switch to the operational MILP for each subproblem:

.. code-block:: bash

   fhops plan rolling examples/med42/scenario.yaml \
     --master-days 56 \
     --sub-days 21 \
     --lock-days 7 \
     --solver mip \
     --mip-solver highs \
     --mip-time-limit 300 \
     --out-json tmp/med42_mip_rolling.json

Outputs
-------
- JSON summary (``--out-json``) including iteration windows, locked counts, objectives, runtimes, and
  warnings.
- CSV of locked assignments (``--out-assignments``) aggregated across all iterations with columns
  ``machine_id, block_id, day``.

Notes
-----
- Locked assignments are treated as immutable across iterations; if a subproblem has no feasible
  availability, the CLI will fail fast with a clear error.
- SA and MILP hooks accept the current locks as incumbents; MILP warm starts are best-effort.
- Telemetry/reporting layers will evolve; current exports are meant to unblock experimentation.
