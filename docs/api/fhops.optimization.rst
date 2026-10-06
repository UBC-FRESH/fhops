``fhops.optimization`` Package
==============================

The optimisation stack converts :class:`fhops.scenario.contract.Problem` objects into either Pyomo MIP
models or heuristic schedules. Use these modules when:

* Building or inspecting the Pyomo model (objective weights, mobilisation constraints, sequencing).
* Running the HiGHS/Gurobi solver via :func:`fhops.optimization.mip.highs_driver.solve_mip`.
* Running simulated annealing / ILS / Tabu heuristics from :mod:`fhops.optimization.heuristics`.

Typical usage:

.. code-block:: python

   from fhops.scenario.io import load_scenario
   from fhops.scenario.contract import Problem
   from fhops.optimization.mip import solve_mip

   pb = Problem.from_scenario(load_scenario("tests/fixtures/regression/regression.yaml"))
   result = solve_mip(pb, time_limit=300)
   if result["has_solution"]:
       print(result["outcome"], result["objective"], len(result["assignments"]))
   else:
       # "infeasible", "no_solution" (time limit) or "error" (see result["solver_error"])
       print(result["outcome"], result["solver_error"])

Since FHOPS 1.0.1 ``solve_mip`` does not raise for infeasible models, time limits without an
incumbent or solver errors; it returns ``has_solution``, ``outcome``, ``solver_error`` and
``warnings`` like :func:`fhops.model.milp.driver.solve_operational_milp`. Only a missing solver
raises :class:`~fhops.optimization.mip.highs_driver.SolverUnavailable`. The bundled examples
(tiny7–large84) are infeasible for this legacy model (see :doc:`../reference/cli`); use the
operational MILP for them.

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

.. automodule:: fhops.optimization.heuristics.sa
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:
