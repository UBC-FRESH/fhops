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
- [x] Create regression scenario set with expected results for automated comparison. *(Added mobilisation/blackout/sequence fixture in `tests/fixtures/regression` exercised by both MIP + SA tests.)*
- [ ] Evaluate Pyomo-to-HiGHS export time and propose decompositions if needed.

## Tests & Benchmarks
- [x] Extend unit/integration tests around the MIP builder.
- [ ] Add performance benchmarks (pytest markers) capturing solve durations and objective values.

## Documentation
- [ ] Update Sphinx API docs for model modules.
- [ ] Add workflow walkthrough detailing how constraints impact solutions.

## Open Questions
- Should we support alternative solvers (CBC, Gurobi) via extras?
- How to expose advanced tuning parameters without overwhelming CLI users?
