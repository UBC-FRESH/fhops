``fhops.evaluation`` Package
============================

The evaluation layer turns solver assignments into KPI-rich reports. It houses deterministic playback,
stochastic extensions, and KPI calculators. Use it to:

* Convert solver outputs into shift/day summaries (:func:`fhops.evaluation.playback.run_playback`).
* Compute KPI bundles for CLI reports or notebooks (:func:`fhops.evaluation.metrics.kpis.compute_kpis`).
* Export CSV/Parquet/Markdown summaries for documentation or telemetry.

Example:

.. code-block:: python

   from fhops.scenario.io import load_scenario
   from fhops.scenario.contract import Problem
   from fhops.optimization.mip import solve_mip
   from fhops.evaluation import compute_kpis

   scenario = load_scenario("examples/tiny7/scenario.yaml")
   problem = Problem.from_scenario(scenario)
   mip_res = solve_mip(problem, time_limit=60)
   kpis = compute_kpis(problem, mip_res["assignments"])
   print(kpis["total_production"], kpis["mobilisation_cost"])

.. automodule:: fhops.evaluation
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: fhops.evaluation.metrics.kpis
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:
