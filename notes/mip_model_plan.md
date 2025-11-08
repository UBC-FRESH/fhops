# MIP Model Expansion Plan

Date: 2025-??-??
Status: Draft — align updates with roadmap Phase 1/2 milestones.

## Objectives
- Catalogue current Pyomo constraints/objectives and identify gaps vs practitioner requirements.
- Implement backlog items (landing capacity variants, mobilisation/setup costs, shift-level capacity, shift-length penalties).
- Encode harvest system sequencing requirements (precedence, machine-worker compatibility) inside the MIP.
- Benchmark solver performance across scenario scales; document tunings and warm-start strategies.

## Tasks
- [x] Map each constraint/objective to source files (`fhops/model` → `optimization/mip`).
- [x] Define parameterisation for new constraints (e.g., mobilisation thresholds, sequencing dependencies, soft landing caps, priority scores). *(Setup-cost penalties wired; thresholds pending distance integration.)*
- [ ] Support schedule locking (pre-assigned machine/block/time decisions) in MIP and heuristics to honour external contracts and immovable commitments.
  - Extend scenario contract + loader to accept a `locked_assignments` structure.
  - Enforce `x[m,b,d] == 1/0` as required in the MIP builder and mirror the rule inside SA.
- [x] Create regression scenario set with expected results for automated comparison. *(Added mobilisation/blackout/sequence fixture in `tests/fixtures/regression` exercised by both MIP + SA tests.)*
- [ ] Evaluate Pyomo-to-HiGHS export time and propose decompositions if needed.
  - Add optional pytest marker/utility to log build/export times for typical fixtures.
  - Document guidance (e.g., warm starts, decomposition candidates) once data collected.
- [ ] Introduce optional objective variants (e.g., maximise production minus mobilisation cost, minimise move count) controlled via scenario flag/CLI.
  - Provide tests ensuring alternative objectives and soft-landing penalties activate correctly.

## Tests & Benchmarks
- [x] Extend unit/integration tests around the MIP builder.
- [ ] Add performance benchmarks (pytest markers) capturing solve durations and objective values.
  - Include locking scenarios to ensure heuristics/MIP produce consistent results.

## Documentation
- [ ] Update Sphinx API docs for model modules.
- [ ] Add workflow walkthrough detailing how constraints impact solutions.
  - Include instructions for schedule locking and objective toggles in docs/README.

## Open Questions
- Should we support alternative solvers (CBC, Gurobi) via extras?
- How to expose advanced tuning parameters without overwhelming CLI users?
