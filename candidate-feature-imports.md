# Candidate Feature Imports & Strategic Enhancements

This backlog captures ideas not yet scheduled on the roadmap. Each entry should note origin,
proposed FHOPS mapping, expected value, and readiness. Update status as investigations progress.

## Operational analytics alignment
- **Origin:** Nemora sampling + ingest modules.
- **Plan:** Expose FHOPS evaluation hooks that accept Nemora-generated stand tables to stress test
  harvesting plans under realistic distributions.
- **Value:** Shared data pipeline across projects, faster scenario setup for joint studies.
- **Status:** Ideation; depends on `notes/simulation_eval_plan.md` outcomes.

## Heuristic operator library expansion
- **Origin:** Forest operations research literature (ILS, Tabu, adaptive large neighbourhood search).
- **Plan:** Implement modular operator registry referenced in `notes/metaheuristic_roadmap.md`.
- **Value:** Improved solution quality on large horizons; facilitates comparative studies.
- **Status:** Requires Phase 2 scheduling.

## Geo-enabled workflows
- **Origin:** Practitioner requests for spatial context in scheduling.
- **Plan:** Add optional GeoPandas pipelines for block/landing geometry validation, with docs in
  Sphinx and CLI toggles.
- **Value:** Bridge to field deployment; clarifies data expectations for GIS teams.
- **Status:** Pending evaluation of `geo` extra adoption.

## Cloud-scale experimentation harness
- **Origin:** Internal HPC pilot.
- **Plan:** Provision CI scripts and Terraform/Ansible templates to launch solver batches on cloud
  instances; integrate with CI/CD plan.
- **Value:** Enables large-scale benchmarking without manual setup.
- **Status:** Deferred until CI/CD pipeline stabilises.
