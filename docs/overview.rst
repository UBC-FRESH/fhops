Overview
========

FHOPS (Forest Harvesting Operations Planning System) provides a Python API and CLI for
constructing, solving, and evaluating harvesting schedules. At its core FHOPS supplies:

- A typed data contract describing blocks, machines, landings, and calendar information.
- A deterministic MIP builder (Pyomo + HiGHS) for exact optimisation.
- Metaheuristic solvers for larger instances where MIP alone is insufficient.
- Evaluation routines to replay schedules, collect KPIs, and explore robustness.

The roadmap in :doc:`roadmap` and the notes under ``notes/`` guide ongoing development. Refer to
:doc:`howto/quickstart` for a hands-on example.
