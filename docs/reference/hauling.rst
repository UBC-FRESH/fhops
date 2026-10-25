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
- :class:`fhops.hauling.network.Truckload` / :class:`fhops.hauling.network.ScheduleProblem` –
  individual loads and normalised Phase II data.
- :func:`fhops.hauling.network.build_schedule_problem` – Phase I result to one-day scheduling data.
- :func:`fhops.hauling.schedule.solve_schedule` – continuous-time truck/loader scheduling MIP.
- :func:`fhops.hauling.schedule.simulate_plan` / :func:`fhops.hauling.schedule.validate_schedule` –
  independent schedule oracles.
- :class:`fhops.hauling.schedule.ScheduleSolveResult` – schedule, truck/loader summaries, plan, and
  solver provenance.
- :class:`fhops.hauling.heuristic.SAConfig` – thesis-derived annealing parameters and operator
  weights.
- :func:`fhops.hauling.heuristic.solve_sa` – route-permutation SA with the SPT decoder.
- :func:`fhops.hauling.heuristic.evaluate_routes` / :func:`fhops.hauling.heuristic.decode_routes` –
  cost evaluation and loader-order decoding.
- :class:`fhops.hauling.heuristic.HaulingSAResult` – best schedule, cost components, search
  provenance, and history.
- :func:`fhops.hauling.integration.scenario_from_operational_plan` – operational assignments to
  hauling supply.
- :func:`fhops.hauling.integration.scenario_from_tactical_plan` – tactical production/demand to
  hauling supply/demand.
- :func:`fhops.hauling.integration.residual_report` – supply/demand residual per log sort.
- :func:`fhops.hauling.reporting.write_flow_run` / :func:`fhops.hauling.reporting.write_schedule_run`
  / :func:`fhops.hauling.reporting.write_solve_run` – stable artefact writers.
- :func:`fhops.hauling.reporting.build_markdown_report` – Markdown run report.

Example
-------

.. code-block:: python

   from fhops.scenario.io import load_scenario

   scenario = load_scenario("examples/hauling/scenario.yaml")
   assert scenario.hauling is not None
   print(scenario.hauling.planning_horizon_days)
   print(scenario.hauling.log_sort_ids())
   print(scenario.hauling.trucks_for("c1", "highway"))
