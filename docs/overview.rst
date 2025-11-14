Overview
========

FHOPS (Forest Harvesting Operations Planning System) provides a Python API and CLI for
constructing, solving, and evaluating harvesting schedules. At its core FHOPS supplies:

- A typed data contract describing blocks, machines, landings, and calendar information.
- A deterministic MIP builder (Pyomo + HiGHS) for exact optimisation.
- Metaheuristic solvers for larger instances where MIP alone is insufficient.
- Evaluation routines to replay schedules, collect KPIs, and explore robustness.
- Scheduling extensions for shift timelines, mobilisation parameters, and synthetic scenario generation scaffolding.

The roadmap in :doc:`roadmap` and the notes under ``notes/`` guide ongoing development. Refer to
:doc:`howto/quickstart` for a hands-on example.

Installation
------------

FHOPS publishes wheels/sdists via Hatch. Once the release candidate is on PyPI, install with::

   pip install fhops

For development or release verification, install Hatch and run the full suite locally::

   pip install hatch
   hatch run dev:suite

Baseline Workflows
------------------

Two canonical scenarios ship with FHOPS:

- ``examples/minitoy`` — minimal CSV/YAML inputs illustrating the scenario contract.
- ``tests/fixtures/regression`` — deterministic fixture covering mobilisation, machine
  blackouts, and harvest-system sequencing with baseline KPI/objective values.

Use the quickstart to validate both scenarios locally and compare CLI output against the
documented baselines before extending the solvers or data contract.

For exhaustive schema details, see :doc:`howto/data_contract`.
