``fhops.scenario`` Package
==========================

This package hosts the scenario contract, IO utilities, and synthetic dataset generator. Use it when
authoring datasets, validating inputs, or programmatically instantiating :class:`fhops.scenario.contract.Problem`
objects before passing them to solvers. The typical workflow is:

1. Define CSV tables + YAML metadata (see :doc:`../howto/data_contract`).
2. Load scenarios with :func:`fhops.scenario.io.load_scenario`.
3. Create a :class:`fhops.scenario.contract.Problem` via ``Problem.from_scenario`` for use with MIP/heuristics.
4. Optionally call :mod:`fhops.scenario.synthetic` helpers to generate benchmark datasets.

.. automodule:: fhops.scenario
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.scenario.contract
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

Quickstart
----------

.. code-block:: python

   from fhops.scenario.io import load_scenario
   from fhops.scenario.contract import Problem

   scenario = load_scenario("examples/tiny7/scenario.yaml")
   problem = Problem.from_scenario(scenario)
   print(problem.days, len(problem.shifts))

Key models:

* :class:`fhops.scenario.contract.Scenario` – Pydantic model for inputs (blocks, machines, timelines).
* :class:`fhops.scenario.contract.Problem` – Derived object used by solvers (`days`, `shifts`, `scenario`).
* :class:`fhops.scenario.contract.MobilisationConfig` / ``TimelineConfig`` – optional extras for mobilisation/shift data.
* :class:`fhops.scenario.contract.ScenarioInitialState` – optional carried-in state (staged inventory, remaining role
  output, head-start shift counts, last block per machine); see :ref:`initial-state`.
* :class:`fhops.scenario.contract.ScheduleLock` – machine/block/day locks with an optional ``shift_id``.

.. automodule:: fhops.scenario.io
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.scenario.synthetic
   :members:
   :undoc-members:
   :show-inheritance:
