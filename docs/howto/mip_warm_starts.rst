Operational MILP Warm Starts
============================

The operational MILP now accepts heuristic schedules as warm starts via ``fhops solve-mip-operational --incumbent seed.csv``. This page documents how to generate those CSVs, what the CLI/API derive from them, and—critically—why the feature is still experimental for medium/large ladders.

Workflow
--------

#. **Generate a candidate schedule.** Use any heuristic command that emits assignments with the canonical column schema::

       fhops solve-heur examples/med42/scenario.yaml \
         --iters 0 \
         --out tmp/med42_greedy_incumbent.csv

   The CSV must include ``machine_id``, ``block_id``, ``day``, and ``shift_id``. If you pass the optional ``assigned`` or ``production`` columns they are honoured when seeding Pyomo variables.

#. **Feed the incumbent to the MILP.** Any ``solve-mip-operational`` invocation can reuse the schedule::

       fhops solve-mip-operational examples/med42/scenario.yaml \
         --solver gurobi \
         --solver-option Threads=36 \
         --solver-option TimeLimit=120 \
         --incumbent tmp/med42_greedy_incumbent.csv \
         --out tmp/med42_mip_seeded.csv

   The CLI rebuilds the :class:`fhops.optimization.operational_problem.OperationalProblem` context, derives the implied transitions, activation binaries, per-role inventories, landing surplus, and leftovers, and then sets Pyomo's ``warmstart=True`` flag before launching the solver.

#. **Inspect the solver log.** Successful warm starts show the candidate objective up-front. When the log contains ``User MIP start did not produce a new incumbent solution`` the solver ignored the seed (usually because it can find a better incumbent through its own heuristics).

Current limitations
-------------------

- The plumbing works end-to-end—tiny7/small21 reuse the incumbent immediately—but med42 and large84 still reject greedy or short SA seeds. Those incumbents complete all blocks in ≈23–47 days, while the MILP needs high-quality assignments that respect every loader/landing constraint; the solver therefore finds its own incumbent faster than it can repair the provided schedule.
- Gurobi and HiGHS require every binary implied by the incumbent (assignment, transition, mobilisation activation, loader buffer) to be populated. The CLI handles this automatically, but if you call :func:`fhops.model.milp.driver.solve_operational_milp` directly you must pass the ``OperationalProblem`` context so the helper can rebuild sequencing state.
- Warm starts are best-effort. Providing an incumbent is always safe, yet you should not expect runtime improvements unless the seed is near-feasible for the operational MILP. Until we develop stronger heuristics (e.g., 60 s SA runs with repairs or rolling-horizon MILPs), treat ``--incumbent`` as a diagnostic tool rather than a guaranteed accelerator.

Practical guidance
------------------

- Capture solver logs with ``--solver-option LogFile=med42.log`` when experimenting so you can confirm whether the incumbent was accepted.
- Budget heuristics so they can produce a schedule that finishes close to the horizon (e.g., SA with ``--iters 2000`` and ``--watch`` set to 60 seconds). Seeds that leave large staged volume or violate sequencing will be discarded.
- Fall back to solver-based heuristics (pure Gurobi/HiGHS) if the warm start keeps getting rejected—the solver is often faster at generating its own incumbent once it hits the strong root relaxation.

Future work
-----------

Warm starts become truly useful once we can:

- Generate med42-quality incumbents that satisfy loader/landing balance (potentially by repairing SA outputs with the SequencingTracker).
- Lock in early-week decisions via rolling-horizon MILPs so the incumbent only needs to cover a subset of shifts at a time.
- Expose benchmark automation that measures “seeded vs unseeded” runtime/gap curves in CI.

Until then, the published CLI/API docs intentionally describe the feature as operational-but-not-yet-practically-useful so users know what to expect.
