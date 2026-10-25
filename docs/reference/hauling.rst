``fhops.hauling`` Package
=========================

The generated API reference is :doc:`../api/fhops.hauling`. This page is the narrative guide.

The package contains the optional operational log-hauling layer. The first task (P11.1) ships the
Pydantic contract; the Phase I flow model, Phase II scheduling model, and Phase III simulated
annealing land in P11.2-P11.4.

Key models
----------

- :class:`fhops.hauling.contract.HaulingConfig` – the optional ``hauling:`` section.
- :class:`fhops.hauling.contract.LogSort` – sorted or unsorted log assortment.
- :class:`fhops.hauling.contract.Contractor` / :class:`fhops.hauling.contract.TruckType` /
  :class:`fhops.hauling.contract.Truck` – the contracted fleet.
- :class:`fhops.hauling.contract.Depot` / :class:`fhops.hauling.contract.DepotLeg` – central depot
  and its travel times.
- :class:`fhops.hauling.contract.SortYard` – storage and processing capacities.
- :class:`fhops.hauling.contract.LoaderLocation` – binding from a FHOPS machine to a pickup or
  delivery location.
- :class:`fhops.hauling.contract.HaulingSupply` / :class:`fhops.hauling.contract.HaulingDemand` /
  :class:`fhops.hauling.contract.HaulArc` – the Phase I flow inputs.
- :class:`fhops.hauling.contract.DriverPolicy` – regular time and overtime rules.
- :class:`fhops.hauling.flow.HaulingFlowProblem` – normalised Phase I data.
- :func:`fhops.hauling.flow.build_flow_problem` / :func:`fhops.hauling.flow.solve_flow` – build and
  solve the monthly flow model.
- :class:`fhops.hauling.flow.FlowSolveResult` – flows, truckloads, inventories, workload, and
  solver provenance.

Example
-------

.. code-block:: python

   from fhops.scenario.io import load_scenario

   scenario = load_scenario("examples/hauling/scenario.yaml")
   assert scenario.hauling is not None
   print(scenario.hauling.planning_horizon_days)
   print(scenario.hauling.log_sort_ids())
   print(scenario.hauling.trucks_for("c1", "highway"))
