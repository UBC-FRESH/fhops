# MIP Model Expansion Plan

Date: 2025-??-??
Status: Draft — align updates with roadmap Phase 1/2 milestones.

## Objectives
- Catalogue current Pyomo constraints/objectives and identify gaps vs practitioner requirements.
- Implement backlog items (landing capacity variants, move/setup costs, shift-length penalties).
- Benchmark solver performance across scenario scales; document tunings and warm-start strategies.

## Tasks
- [ ] Map each constraint/objective to source files (`fhops/model`).
- [ ] Define parameterisation for new constraints (e.g., soft landing caps, priority scores).
- [ ] Create regression scenario set with expected results for automated comparison.
- [ ] Evaluate Pyomo-to-HiGHS export time and propose decompositions if needed.

## Tests & Benchmarks
- [ ] Extend unit/integration tests around the MIP builder.
- [ ] Add performance benchmarks (pytest markers) capturing solve durations and objective values.

## Documentation
- [ ] Update Sphinx API docs for model modules.
- [ ] Add workflow walkthrough detailing how constraints impact solutions.

## Open Questions
- Should we support alternative solvers (CBC, Gurobi) via extras?
- How to expose advanced tuning parameters without overwhelming CLI users?
