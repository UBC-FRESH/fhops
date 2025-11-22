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

   pb = Problem.from_scenario(load_scenario("examples/minitoy/scenario.yaml"))
   result = solve_mip(pb, time_limit=300)
   assignments = result["assignments"]
   print(result["objective"], len(assignments))

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
