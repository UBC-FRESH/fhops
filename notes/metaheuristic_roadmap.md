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
- [x] **Operator registry scaffold:** create a registry for heuristic operators (swap, move, insert, mobilisation-aware shake) with enable/weight flags surfaced via `solve-heur` and benchmark CLI options. Implement telemetry hooks for acceptance counts per operator.
- [ ] **Advanced neighbourhoods:** add shift-aware block insertion (machine ↔ shift reassignment), cross-machine exchange, and mobilisation-sensitive diversification moves. Benchmark each operator on minitoy/med42/large84 to establish performance impacts.
- [ ] **Tabu Search prototype:** implement a Tabu neighbourhood on top of the registry (tabu tenure, aspiration criteria) and compare results against SA in the benchmarking harness. Decide whether to expose as `fhops solve-tabu`.
- [ ] **ILS / Hybrid solver:** design an Iterated Local Search or MIP warm-start hybrid using the registry operators. Document configuration defaults and add harness support for hybrid runs.
- [ ] **Benchmark reporting enhancements:** extend `fhops bench suite` outputs with per-operator usage metrics, solver comparisons (SA/Tabu/Hybrid), and provide summary plots/tables for Sphinx docs.
- [ ] **Documentation updates:** draft a Sphinx how-to covering heuristic configuration presets, registry usage, and interpreting the new benchmarking metrics.

### Subtasks for Operator Registry Scaffold
1. **Registry data model**  
   - Introduce an `Operator` protocol (name, apply function, metadata hooks) and a `OperatorRegistry` class living under `fhops.optimization.heuristics.registry`.  
   - Default registry should register existing `swap` and `move` implementations with optional weight/enable flags.
2. **SA integration**  
   - Refactor `_neighbors` to consume the registry API (pull weighted operator, generate candidate, run sanitiser).  
   - Ensure lock/availability checks remain in the shared sanitizer so all operators inherit the safeguards.
3. **CLI + config surface**  
   - Extend `solve_sa` signature and CLI (`solve-heur`, `bench suite`) to accept `--operator=swap --operator=move --operator-weight swap=2` style options; fall back to defaults when unspecified.  
   - Persist operator settings into the returned `meta` telemetry for benchmarking comparisons.
4. **Telemetry instrumentation**  
   - Track per-operator proposal/accept counts inside the SA loop; emit JSON serialisable stats (`meta["operators"] = {...}`) and append to benchmark summary CSV/JSON.
5. **Testing**  
   - Add unit tests covering registry registration, toggle/weight effects, and CLI parsing (convert CLI args → registry config).  
   - Update regression harness to assert operator telemetry fields exist and are stable for baseline seeds.
6. **Docs & notes sync**  
   - Document registry usage in `docs/reference/cli.rst` (new CLI flags) and seed a how-to stub for advanced tuning.  
   - Update this roadmap and the Phase 2 checklist once registry lands.

#### Subsubtasks for (1) Registry data model
- [x] Define `OperatorContext` dataclass capturing `(pb, schedule, sanitizer, rng)` to avoid tight coupling inside operator functions.
- [x] Create `Operator` protocol with `name: str`, `weight: float`, and `apply(context) -> Schedule | None`.
- [x] Implement `OperatorRegistry` with: `register`, `get(name)`, `enabled()` iterator, `configure({name: weight})`, and default `from_defaults()` factory.
- [x] Port existing `swap`/`move` logic into standalone operator functions referencing the shared sanitizer; register them in `from_defaults()`.
- [x] Add module-level tests ensuring default registry exposes `swap`/`move`, weight updates propagate, and disabled operators are skipped.

#### Subsubtasks for (2) SA integration
- [x] **Registry wiring:** replace `_neighbors` direct logic with registry iteration, supplying a reproducible RNG seeded from `solve_sa` parameters.
- [x] **Shared sanitizer:** extract the availability/lock/landing-cap checks into a reusable sanitizer function leveraged by all operators, ensuring parity with current enforcement.
- [x] **Operator weighting:** add simple selection logic (e.g., weighted roulette) to pick operators proportionally to their configured weights; fall back to sequential iteration when only one operator is enabled.
- [x] **Schedule passthrough:** ensure operators can return `None` when no move is possible and `_neighbors` skips them gracefully to avoid empty neighbour lists.
- [x] **Regression verification:** rerun benchmark and regression suites to confirm SA outputs remain stable; adjust fixtures/notes if weighted operator selection affects acceptance metrics.

#### Subsubtasks for (3) CLI + config surface
- [x] **Solve CLI flags:** extend `fhops.cli.main.solve_heur` with `--operator` and `--operator-weight` options (multi-use) to enable/disable operators and tune weights; update SA entry point to parse the configuration into registry settings.
- [x] **Benchmark harness wiring:** propagate operator configuration options through `fhops.cli.benchmarks.run_benchmark_suite` and CLI command; ensure summary outputs include the operator settings used.
- [x] **Default presets:** introduce sensible presets (e.g., `--preset greedy`, `--preset diversify`) or shortcuts for common configurations, and document default weight values.
- [x] **Validation & error messages:** add user-friendly errors for unknown operators or malformed weight arguments; include unit tests covering argument parsing.
- [x] **Documentation & notes:** update `docs/reference/cli.rst` (solve/bench sections) with examples, and note the new surface area in this roadmap plus any relevant notes files.

#### Plan: Operator Preset Shortcuts
- **Preset catalog** — Maintain a declarative preset mapping (balanced, swap-only, move-only, swap-heavy, diversify) with clear goals, each mapping to operator weight dicts.
- **Chaining support** — Allow multiple presets via comma-separated values or repeated `--operator-preset`, merging in order; zero weights disable operators.
- **User overrides** — Apply presets first, then explicit `--operator`/`--operator-weight` overrides to honour user intent; log final configuration.
- **Discovery** — Add a `--list-operator-presets` flag that prints available presets with descriptions and weight tables.
- **Custom presets (future)** — Consider loading user-defined presets from a config file (`~/.fhops/heuristics/presets.yaml`) merged with built-ins.
- **Documentation** — Expand CLI docs with preset tables/examples and note merging semantics; add roadmap entry once feature lands.

#### Subsubtasks for (4) Telemetry instrumentation
- [x] **Per-operator counters:** track proposals/acceptances per operator within `solve_sa` and surface them in the returned `meta["operators_stats"]` object.
- [x] **Benchmark aggregation:** extend `_record_metrics` to persist operator stats (e.g., proposals, acceptance rate) into summary outputs/CSV for SA runs.
- [x] **CLI display:** optionally print a concise operator stats table in `solve-heur` when `--debug` or a new `--show-operator-stats` flag is used.
- [x] **Tests:** add unit/integration coverage verifying counters increment correctly (e.g., deterministic neighbour selection, smoke test via minitoy benchmark).
- [x] **Documentation:** document telemetry fields in CLI reference and roadmap, highlighting how to interpret operator statistics during tuning sessions.
- [x] **Persistent telemetry log:** design a structured log (e.g., newline-delimited JSON or SQLite) keyed by scenario/operator config capturing run metadata (seed, iterations, operator stats, acceptance rate, objective). Provide a helper to append entries and document the schema for future ML/DL hyperparameter tuning workflows.

#### Subsubtasks for (5) Documentation updates
- [x] **Telemetry schema doc:** add a developer note (``docs/reference/telemetry.rst``) that explains the JSONL schema, fields, and example entries produced by `--telemetry-log`.
- [x] **How-to section:** extend the SA how-to with guidance on interpreting `operators_stats` (e.g., acceptance thresholds, when to adjust weights).
- [x] **Benchmark output docs:** document the new ``operators_stats`` column in benchmark summaries and show how to parse it programmatically.
- [x] **Notes sync:** reference the hyperparameter tuning plan and telemetry schema in `notes/metaheuristic_hyperparam_tuning.md` for future automation work.
- [x] **Changelog hook:** ensure the changelog summarises the telemetry documentation work once the above items land.

### Subtasks for Advanced neighbourhoods
- [ ] **Design & interfaces:** define new operators (block insertion, cross-machine exchange, mobilisation-aware shake), specifying preconditions, behaviour, and additional context needed (e.g., distance lookups).
- [ ] **Implementation:** add operator classes that reuse the shared sanitizer, register them with default weights, and ensure plan cloning stays efficient.
- [ ] **Weighting & presets:** set sensible defaults, expose new presets (e.g., `explore`, `mobilisation`), and update CLI docs/config helpers.
- [ ] **Benchmark evaluation:** compare baseline vs. extended operator sets across minitoy/med42/large84, capturing telemetry and summarising outcomes in notes/changelog.
- [ ] **Testing & regression:** expand unit/regression coverage to exercise new operators (window constraints, mobilisation penalties, lock handling).

##### Plan – Advanced neighbourhoods: Design & interfaces
- Catalogue candidate operators with design goals:
  * **BlockInsertionOperator** — relocate a block assignment to a different shift (same or different machine) within availability/windows to reduce congestion.
  * **CrossExchangeOperator** — exchange assignments between machines across shifts to rebalance workloads and unlock sequencing opportunities.
  * **MobilisationShakeOperator** — intentionally trigger mobilisation-heavy moves to escape local optima while respecting mobilisation thresholds.
- For each operator, specify:
  * **Preconditions** – required machine roles, availability, locks, mobilisation data.
  * **Inputs** – mobilisation distance lookup, block windows, landing capacities (reuse data prepared in `_evaluate`).
  * **Schedule deltas** – which `(machine, day, shift)` entries change and how vacated slots are handled.
  * **Telemetry fields** – additional metrics such as `distance_delta`, `mobilisation_delta`, or `window_shifted` to add to `operators_stats`.
- Extend `OperatorContext` (optional) with references like `distance_lookup`, `block_windows`, and `landing_capacity`, defaulting to `None` for backwards compatibility.
- Draft pseudo-code for each operator capturing candidate selection, validation order, and fallback behaviour (return `None` when no feasible move exists).

##### Plan – Advanced neighbourhoods: Implementation
- Implement operator classes (e.g., `InsertionOperator`, `ExchangeOperator`, `MobilisationShakeOperator`).
- Use helper utilities to clone plans and ensure sanitizer is applied uniformly.
- Register new operators in `OperatorRegistry.from_defaults()` with guarded default weights.
- Update preset definitions to include new operators where appropriate.

##### Plan – Advanced neighbourhoods: Weighting & presets
- Design new presets (`explore`, `mobilisation`, etc.) combining existing and new operators with documented rationale.
- Allow CLI overrides to combine presets with explicit weights; ensure `--list-operator-presets` reflects new options.
- Document default weights and recommended use cases (e.g., mobilisation-heavy scenarios).

##### Plan – Advanced neighbourhoods: Benchmark evaluation
- Extend benchmark harness to compare baseline vs. preset configurations; log objective, runtime, and operator stats.
- Analyse telemetry JSONL to quantify improvements/changes; summarise findings in notes and changelog entries.
- Decide on default inclusion of new operators based on benchmark evidence.

##### Plan – Advanced neighbourhoods: Testing & regression
- Add unit tests verifying each operator respects availability, windows, locks, and mobilisation rules.
- Update regression fixtures (e.g., mobilisation-heavy scenario) to ensure new operators improve or at least maintain objective.
- Seed RNG deterministically so regression benchmarks remain reproducible.
