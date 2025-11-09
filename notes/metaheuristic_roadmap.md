# Metaheuristic Roadmap

Date: 2025-??-??
Status: Draft — baseline SA exists; expansion pending Phase 2.

## Objectives
- Document current simulated annealing defaults (neighbourhood operators, cooling schedule) and establish reproducible benchmarks across scenario sizes.
- Upgrade simulated annealing implementation and evaluate alternative heuristics (Tabu, ILS, ALNS).
- Provide configuration presets accessible via CLI and documented in Sphinx.

## Planned Tasks
- [x] Document current SA parameter defaults and tuning rationale. *(Probability: initial temperature `max(1.0, best_score/10)`, decay `0.995`, restarts every 100 steps, neighbourhoods: day swap + intra-machine move; exposed via `--iters`, `--seed` in CLI.)*
- [x] Capture SA metrics via benchmarking harness (objective gap vs MIP, runtime, acceptance ratio).
- [ ] Implement operator registry to plug in new neighbourhood moves (swap, insert, block reassignment) with shift-aware variants and expose tuning via CLI.
- [ ] Prototype Tabu Search with aspiration criteria and compare against SA baselines.
- [ ] Investigate hybrid approaches (MIP warm start + heuristic refinement).

## Testing & Evaluation
- [x] Create benchmark suite capturing objective value vs runtime for standard scenarios (minitoy/med42/large84 via `fhops bench suite`).
- [ ] Add stochastic regression tests with fixed seeds.
- [ ] Consider property-based tests for invariants (e.g., feasibility of generated schedules).

## Documentation
- [ ] Write Sphinx how-to for heuristic configuration.
- [ ] Surface benchmarking results in docs (tables/plots).

## Open Questions
- Do we need GPU-friendly implementations for large instances?
- How to expose experimental operators without destabilising default behaviour?

## Shift-Aware Simulated Annealing Upgrade (Phase 2 focus)
- [x] **Schedule representation:** extend `Schedule.plan` to track `(day, shift_id)` assignments, ensuring loaders/serialisers produce shift-aware DataFrames. *(SA `Schedule`, evaluator, neighbours, and outputs now store and emit shift-indexed plans; tests updated via helper converters.)*
- [x] **Initialisation & locks:** update `_init_greedy` and lock handling to honour shift calendar availability, blackout windows, and pre-fixed `(machine, day, shift)` slots. *(Greedy seeding skips shift-level outages/blackouts; evaluator penalties now use `(machine, day, shift)` keys to match MIP handling.)*
- [x] **Neighbourhoods:** port swap/move operators to iterate over shift indices, maintaining feasibility (machine capacity, landing caps, mobilisation cooldowns). *(Neighbour sanitisation now enforces shift availability and blackout checks; benchmark fixtures updated for new SA behaviour.)*
- [x] **Objective evaluation:** refactor `_evaluate` to score shift-by-shift, mirroring the shift-indexed mobilisation penalties, transition weights, and landing slack terms used in the MIP. *(Evaluation now respects shift-specific availability, blackout penalties, landing slack, and mobilisation transitions using `(machine, day, shift)` keys.)*
- [x] **CLI & benchmarking:** ensure `solve-sa` and the benchmark harness emit shift-aware assignment tables/metrics aligned with KPIs. *(Solver exports already carry `shift_id`; CLI/docs updated to highlight the column and locking tests assert shift-level fixes.)*
- [x] **Tests/regressions:** refresh SA-specific unit/integration tests and regression baselines to confirm parity with the shift-indexed MIP outputs. *(Regression harness now asserts shift-aware assignments and updated acceptance metrics; minitoy fixture refreshed.)*

## Metaheuristic Expansion (next milestones)
- [ ] **Operator registry scaffold:** create a registry for heuristic operators (swap, move, insert, mobilisation-aware shake) with enable/weight flags surfaced via `solve-heur` and benchmark CLI options. Implement telemetry hooks for acceptance counts per operator.
- [ ] **Advanced neighbourhoods:** add shift-aware block insertion (machine ↔ shift reassignment), cross-machine exchange, and mobilisation-sensitive diversification moves. Benchmark each operator on minitoy/med42/large84 to establish performance impacts.
- [ ] **Tabu Search prototype:** implement a Tabu neighbourhood on top of the registry (tabu tenure, aspiration criteria) and compare results against SA in the benchmarking harness. Decide whether to expose as `fhops solve-tabu`.
- [ ] **ILS / Hybrid solver:** design an Iterated Local Search or MIP warm-start hybrid using the registry operators. Document configuration defaults and add harness support for hybrid runs.
- [ ] **Benchmark reporting enhancements:** extend `fhops bench suite` outputs with per-operator usage metrics, solver comparisons (SA/Tabu/Hybrid), and provide summary plots/tables for Sphinx docs.
- [ ] **Documentation updates:** draft a Sphinx how-to covering heuristic configuration presets, registry usage, and interpreting the new benchmarking metrics.
