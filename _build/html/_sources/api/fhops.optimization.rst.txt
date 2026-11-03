``fhops.optimization`` Package
==============================

The optimisation stack converts :class:`fhops.scenario.contract.Problem` objects into either Pyomo MIP
models or heuristic schedules. Use these modules when:

* Running simulated annealing / ILS / Tabu heuristics from :mod:`fhops.optimization.heuristics`.
* Building the operational problem context
  (:func:`fhops.optimization.operational_problem.build_operational_problem`) consumed by the
  operational MILP (:func:`fhops.model.milp.driver.solve_operational_milp`) and the heuristics.

The exact model is the operational MILP (:mod:`fhops.model.milp`, ``fhops solve-mip-operational``),
the formulation documented in the FHOPS paper:

.. code-block:: python

   from fhops.scenario.io import load_scenario
   from fhops.scenario.contract import Problem
   from fhops.optimization.operational_problem import build_operational_problem
   from fhops.model.milp.driver import solve_operational_milp

   pb = Problem.from_scenario(load_scenario("examples/tiny7/scenario.yaml"))
   ctx = build_operational_problem(pb)
   result = solve_operational_milp(ctx.bundle, time_limit=300, context=ctx)
   if result["has_solution"]:
       print(result["outcome"], result["objective"], len(result["assignments"]))
   else:
       # "infeasible", "no_solution" (time limit) or "error" (see result["solver_error"])
       print(result["outcome"], result["solver_error"])

Deprecated legacy MIP (1.0.1, #127)
-----------------------------------

:func:`fhops.optimization.mip.solve_mip` and :func:`fhops.optimization.mip.builder.build_model`
remain importable for API compatibility but emit
:class:`~fhops.optimization.mip.deprecation.LegacyMipDeprecationWarning` (a
:class:`DeprecationWarning`, shown for calls from scripts/notebooks and under pytest):

* ``solve_mip(pb, time_limit=60, driver="auto", debug=False)`` delegates to the operational MILP
  (:func:`~fhops.optimization.mip.highs_driver.solve_with_operational_milp`). It keeps the 1.0.1
  result contract (``objective``, ``assignments``, ``has_solution``, ``outcome``,
  ``solver_status``, ``termination_condition``, ``solver_error``, ``warnings``; plus
  ``production``, ``warm_start`` and ``solver``), never raises for infeasible models, time limits
  or solver errors, and raises :class:`~fhops.optimization.mip.highs_driver.SolverUnavailable` only
  for a missing solver and ``ValueError`` for an unknown driver. Legacy ``driver`` names map to
  operational solvers via :func:`~fhops.optimization.mip.highs_driver.operational_solver_for_driver`
  (``auto`` → Gurobi when installed, else HiGHS; HiGHS drivers → ``highs``; ``gurobi`` /
  ``gurobi-appsi`` / ``gurobi-direct`` → ``gurobi`` / ``appsi_gurobi`` / ``gurobi_direct``).
  Objectives are operational MILP objectives, not comparable with 1.0.0 ``solve_mip`` values.
* ``build_model(pb)`` still builds the legacy day-level Pyomo model, which no solver uses. Its
  loader-buffer constraint demands ``−batch`` m³ of buffer in the first shift, so it is infeasible
  for every scenario with a loader role (every bundled example, also at v1.0.0). Use
  :func:`fhops.model.milp.operational.build_operational_model` instead.

.. automodule:: fhops.optimization
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: fhops.optimization.mip.builder
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.optimization.mip.highs_driver
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.optimization.mip.deprecation
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.optimization.heuristics.sa
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:
