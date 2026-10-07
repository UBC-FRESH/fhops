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

   The CLI rebuilds the :class:`fhops.optimization.operational_problem.OperationalProblem` context, derives the implied machine positions and moves, activation binaries, per-role inventories, landing surplus, and leftovers, and then hands the seeded values to the solver as a MIP start (see :ref:`mip-warm-start-solvers`).

   With the default open-source solver the same workflow is::

       fhops solve-mip-operational examples/tiny7/scenario.yaml \
         --time-limit 60 --out tmp/tiny7_mip.csv
       fhops solve-mip-operational examples/tiny7/scenario.yaml \
         --time-limit 5 --incumbent tmp/tiny7_mip.csv --out tmp/tiny7_mip_seeded.csv

   and the CLI reports how the start was used::

       Warm start: method=appsi_highs solver=appsi_highs seeded_slots=14 (accepted)
         MIP start solution is feasible, objective value is 279.796036

#. **Inspect the solver log.** Successful warm starts show the candidate objective up-front. HiGHS prints ``MIP start solution is feasible, objective value is …``; when it instead reports ``Attempting to find feasible solution by solving LP for user-supplied values of discrete variables`` followed by ``Model status : Infeasible`` the seed was rejected. With Gurobi, ``User MIP start did not produce a new incumbent solution`` means the solver ignored the seed (usually because it can find a better incumbent through its own heuristics). Add ``--debug`` to stream the full solver log.

.. _mip-warm-start-solvers:

Solver support
--------------

.. list-table::
   :header-rows: 1
   :widths: 22 40 38

   * - ``--solver``
     - How the incumbent reaches the solver
     - Feedback
   * - ``highs`` (default), ``appsi_highs``
     - Pyomo's default ``highs`` plugin (``pyomo.contrib.solver``) rejects the ``warmstart`` keyword, so seeded solves switch to the APPSI HiGHS interface (``appsi_highs``), which passes every seeded variable value to ``highspy.Highs.setSolution``. Unseeded solves keep using ``highs``.
     - The HiGHS log is captured; the CLI prints ``accepted``/``rejected`` plus the HiGHS MIP-start lines and telemetry records them under ``extra.warm_start``.
   * - ``gurobi``, ``gurobi_direct``, ``gurobi_persistent``, ``cplex``, ``cbc`` (≥ 2.8)
     - Unchanged: Pyomo's ``solve(..., warmstart=True)`` (only when the plugin reports ``warm_start_capable()``).
     - Read the solver log (``--debug`` or e.g. ``--solver-option LogFile=run.log``); ``accepted`` is reported as unknown.
   * - anything else (e.g., ``glpk``)
     - Solved **without** the incumbent; :class:`fhops.model.milp.driver.MilpWarmStartWarning` is emitted.
     - ``Warm start not used`` in the CLI output.

From Python, :func:`fhops.model.milp.driver.solve_operational_milp` returns the same information in ``result["warm_start"]`` (``method``, ``solver``, ``seeded_slots``, ``accepted``, ``acceptance``, ``solver_messages``). A solve stopped by its time limit still returns the best incumbent it holds—which, for an accepted warm start, is at least as good as the seed.

Landing capacity is a hard per-shift-slot constraint of the MILP when ``landing_surplus`` is
weighted 0 (1.0.1, #125). Since #140 the heuristics' repair also keeps every slot within a hard
landing capacity, on single-shift days too, so their schedules are landing-feasible MILP starts:
the ``med42`` greedy incumbent above (``--iters 0``) is accepted by HiGHS (``seeded_slots=198
(accepted)``, MIP start objective 13769.68; the heuristic objective of the same plan is 13392.56
because the heuristics also charge mobilisation for moves across idle slots). Before #140 the repair
guarded landings on multi-shift days only, the med42 greedy incumbent overloaded single-shift
landings and HiGHS rejected it (``seeded_slots=212 (rejected)``). Heuristic plans searched with a
positive ``landing_surplus`` weight (e.g. the Tiny7/Small21 automatic overrides, see
:ref:`heuristic-objective-weights`) can still overload landings and are rejected by a MILP with a
hard capacity. Seeding pays off: on the
3-shift BC case study ``ka_6`` HiGHS finds no incumbent of its own within 30 minutes, while the SA
plan (1500 iterations) is accepted and proven optimal in about a minute.

HiGHS does not always log a verdict about the MIP start (e.g. on large models stopped by a time limit). ``accepted`` then defaults to ``None`` unless acceptance can be inferred, in which case ``accepted=True`` and ``acceptance="inferred"`` (``"log"`` when the verdict comes from the HiGHS log). The rule: a solution was returned and either (a) its assignment variables ``x`` equal the seeded ones, or (b) the seeded point satisfied every model constraint (FHOPS records the seeded values and checks them after the solve, only when needed; tolerance 1e-6), so HiGHS could adopt it as its first incumbent, and the returned objective is at least the seed objective. The CLI prints a note when acceptance was inferred.

Solve outcomes
--------------

The driver never raises because a model is infeasible, a time limit was reached without an incumbent, or the solver failed; it reports these cases (1.0.1, #115):

- ``has_solution`` / ``objective``: ``objective`` is ``None`` and ``assignments`` is an empty table with the usual columns when no feasible solution was loaded.
- ``outcome``: ``optimal``, ``feasible`` (incumbent at a limit), ``infeasible``, ``no_solution`` (limit without incumbent), or ``error``.
- ``solver_error``: set for genuine solver failures rather than infeasibility, e.g. HiGHS refusing ``threads=1`` after its global scheduler was initialised with another thread count in the same process (``ERROR: Option 'threads' is set to 1 but global scheduler has already been initialized …``), or any exception the solver interface raises — since 1.0.1 (#139) also ``gurobipy.GurobiError`` for a missing licence or a model too large for the size-limited licence that ships with ``pip install gurobipy`` (``GurobiError: Model too large for size-limited license; …``). The CLI prints it and exits with status 1.
- ``warnings``: locks the model dropped or pinned to idle instead of becoming infeasible, and solver fall-backs (below).
- ``solver``: the ``SolverFactory`` name that produced the result.

``--solver auto`` (``solver="auto"``) uses Gurobi when ``SolverFactory("gurobi")`` is available and HiGHS otherwise. When the Gurobi run fails (``solver_error``, e.g. the size-limited licence on small21), the model is solved again with HiGHS, a :class:`fhops.model.milp.driver.MilpSolverFallbackWarning` is emitted and ``warnings`` starts with ``gurobi failed (…); falling back to highs (solver=auto).``. The deprecated ``solve_mip`` / ``fhops solve-mip --driver auto`` follow the same rule. Solver-specific ``--solver-option`` values are forwarded to every solver tried.

Every solver path calls Pyomo with ``load_solutions=False`` and loads a solution only when the solver holds one (APPSI ``load_vars()``, otherwise ``model.solutions.load_from(results)``). Exported ``production`` values are clamped at 0 (no ``-0.0``).

Current limitations
-------------------

- The plumbing works end-to-end—tiny7/small21 reuse the incumbent immediately—but med42 and large84 still reject greedy or short SA seeds. Those incumbents complete all blocks in ≈23–47 days, while the MILP needs high-quality assignments that respect every loader/landing constraint; the solver therefore finds its own incumbent faster than it can repair the provided schedule.
- Gurobi and HiGHS require every binary implied by the incumbent (assignment, activation, head-start waiver, loader tail) to be populated, and the continuous position/move variables should match it. The CLI handles this automatically, but if you call :func:`fhops.model.milp.driver.solve_operational_milp` directly you must pass the ``OperationalProblem`` context so the helper can rebuild sequencing state.
- Warm starts are best-effort. Providing an incumbent is always safe, yet you should not expect runtime improvements unless the seed is near-feasible for the operational MILP. Until we develop stronger heuristics (e.g., 60 s SA runs with repairs or rolling-horizon MILPs), treat ``--incumbent`` as a diagnostic tool rather than a guaranteed accelerator.

Practical guidance
------------------

- Capture solver logs with ``--solver-option LogFile=med42.log`` (Gurobi) or ``--solver-option log_file=med42.log`` (HiGHS) when experimenting so you can confirm whether the incumbent was accepted.
- Budget heuristics so they can produce a schedule that finishes close to the horizon (e.g., SA with ``--iters 2000`` and ``--watch`` set to 60 seconds). Seeds that leave large staged volume or violate sequencing will be discarded.
- Fall back to solver-based heuristics (pure Gurobi/HiGHS) if the warm start keeps getting rejected—the solver is often faster at generating its own incumbent once it hits the strong root relaxation.

Future work
-----------

Warm starts become truly useful once we can:

- Generate med42-quality incumbents that satisfy loader/landing balance (potentially by repairing SA outputs with the SequencingTracker).
- Lock in early-week decisions via rolling-horizon MILPs so the incumbent only needs to cover a subset of shifts at a time.
- Expose benchmark automation that measures “seeded vs unseeded” runtime/gap curves in CI.

Until then, the published CLI/API docs intentionally describe the feature as operational-but-not-yet-practically-useful so users know what to expect.
