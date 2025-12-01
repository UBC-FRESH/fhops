# MIP Model Expansion Plan

Date: 2025-??-??
Status: Draft — align updates with roadmap Phase 1/2 milestones.

## Objectives
- Catalogue current Pyomo constraints/objectives and identify gaps vs practitioner requirements.
- Implement backlog items (landing capacity variants, mobilisation/setup costs, shift-level capacity, shift-length penalties).
- Encode harvest system sequencing requirements (precedence, machine-worker compatibility) inside the MIP.
- Benchmark solver performance across scenario scales; document tunings and warm-start strategies.
- Transition the MIP builder from day-indexed to shift-indexed decision variables to align with Phase 2 scheduling goals.

### Current Objective/Constraint Coverage (2025-11-08 audit)
- MIP objective supports production and mobilisation weights only; no explicit move-count or landing slack penalties yet.
- SA heuristic mirrors production minus mobilisation cost but ignores `ObjectiveWeights` (fixed weights of 1.0) and lacks move/slack penalties.
- Landing capacity is hard (no slack variables or penalties); per-machine shift limits still tied strictly to calendar availability.
- No instrumentation yet for build/export timing measurements.

## Tasks
- [x] Map each constraint/objective to source files (`fhops/model` → `optimization/mip`).
- [x] Define parameterisation for new constraints (e.g., mobilisation thresholds, sequencing dependencies, soft landing caps, priority scores). *(Setup-cost penalties wired; thresholds pending distance integration.)*
- [x] Support schedule locking (pre-assigned machine/block/time decisions) in MIP and heuristics to honour external contracts and immovable commitments.
  - Scenario contract + loader now accept a `locked_assignments` structure.
  - MIP builder fixes `x[m,b,d]` binaries accordingly and SA enforces the same in `_init_greedy`, `_evaluate`, and neighbourhood sanitisation.
- [x] Create regression scenario set with expected results for automated comparison. *(Added mobilisation/blackout/sequence fixture in `tests/fixtures/regression` exercised by both MIP + SA tests.)*
- [ ] Evaluate Pyomo-to-HiGHS export time and propose decompositions if needed.
  - Add optional pytest marker/utility to log build/export times for typical fixtures.
  - Document guidance (e.g., warm starts, decomposition candidates) once data collected.
- [x] Introduce optional objective variants (e.g., production vs mobilisation weighting) controlled via scenario flag/CLI.
  - `ObjectiveWeights` now expose production, mobilisation, and transition weights; both the MIP builder and SA heuristic honour them.
  - TODO: evaluate additional variants (e.g., landing-cap slack penalties, move-count-only optimisation) once mobilisation baselines are stabilised.

## Tests & Benchmarks
- [x] Extend unit/integration tests around the MIP builder.
- [x] Add performance benchmarks (pytest markers) capturing solve durations and objective values.
- [ ] Introduce shift-indexed sets/variables (machines × blocks × shifts), update mobilisation/landing constraints, and retain compatibility with legacy day-only scenarios.
  - Add builder utilities that expand `(day, shift)` pairs based on `TimelineConfig` and synthesise a default `S1` shift when missing.
  - Update mobilisation, landing, locking, and sequencing constraints to iterate across shift tuples, ensuring data contract + CLI toggles stay aligned.
  - Include locking scenarios to ensure heuristics/MIP produce consistent results across day-only and shift-aware inputs (tests w/ regression fixtures).

## Documentation
- [ ] Update Sphinx API docs for model modules.
- [ ] Add workflow walkthrough detailing how constraints impact solutions.
  - Include instructions for schedule locking and objective toggles in docs/README.
- Landing slack variables are now available when `ObjectiveWeights.landing_surplus > 0`; heuristic mirrors penalty-based slack handling. Performance benchmarking still outstanding.

### Shift-Based Scheduling Migration Checklist — 2025-11-09
1. **Data Contract & Problem Formulation**
   - Consume `TimelineConfig.shift_definitions` when building `Problem` objects; add helper to emit `(day, shift)` tuples as the canonical time set.
   - Extend `ObjectiveWeights`/`MobilisationConfig` hooks so per-shift penalties can be attached later without refactoring variable domains again.
2. **Variable & Constraint Updates**
   - Re-index assignment binaries `x[m, b, d]` → `x[m, b, d, s]`, mobilisation transitions `y[m, prev, curr, d]` → `y[m, prev, curr, d, s]`, landing slack, and sequencing constraints.
   - Optimise variable counts by skipping shifts where machines are unavailable (pre-filter via availability tensor).
   - Add unit tests confirming day-aggregated production equals the sum over shifts and that blackout shifts zero out decision vars.
3. **Solver Outputs & Interop**
   - Update Pyomo-to-result adapters to emit shift-aware schedule records; heuristics should already plan in shifts once we migrate `_iter_moves`.
   - Ensure CLI/export paths (playback, KPI, benchmark harness) pull shift-level data when present and gracefully degrade for day-only scenarios.
4. **Validation & Benchmarks**
   - Refresh regression fixtures to include both single-shift and multi-shift scenarios.
   - Capture build/solve timing deltas before/after the change to document overhead and guide future decomposition work.

## Open Questions
- Should we support alternative solvers (CBC, Gurobi) via extras?
- How to expose advanced tuning parameters without overwhelming CLI users?
