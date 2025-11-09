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
- [x] Add parallel execution pathways (multi-start seeds/presets and batched neighbour evaluation) to leverage multi-core environments while keeping the single-thread solver as the default path. *(Parallelism should be opt-in/feature-flagged so we can disable it quickly if instability appears.)*
- [x] Implement operator registry to plug in new neighbourhood moves (swap, insert, block reassignment) with shift-aware variants and expose tuning via CLI. *(Registry + advanced operators shipped; CLI/presets documented, regression/benchmarks updated.)*
- [x] Prototype Tabu Search with aspiration criteria and compare against SA baselines.
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
- [x] **Advanced neighbourhoods:** add shift-aware block insertion (machine ↔ shift reassignment), cross-machine exchange, and mobilisation-sensitive diversification moves. Benchmark each operator on minitoy/med42/large84 to establish performance impacts.
- [x] **SA parallel execution (opt-in):** deliver multi-start orchestration, batched neighbour evaluation, CLI/config integration, and profiling/documentation for the new knobs.
- [x] **Tabu Search prototype:** implement a Tabu neighbourhood on top of the registry (tabu tenure, aspiration criteria) and compare results against SA in the benchmarking harness. *(Prototype available via `fhops solve-tabu` and `fhops bench suite --include-tabu`; keep Tabu opt-in until future tuning narrows the SA performance gap.)*
- [x] **ILS / Hybrid solver:** design an Iterated Local Search or MIP warm-start hybrid using the registry operators. Document configuration defaults and add harness support for hybrid runs. *(ILS CLI/docs/telemetry live; regression + benchmark suite captured in `tmp/bench_ils`; solver remains opt-in pending further tuning.)*
- [x] **Benchmark reporting enhancements:** extend `fhops bench suite` outputs with per-operator usage metrics, solver comparisons (SA/Tabu/Hybrid), and provide summary plots/tables for Sphinx docs.
- [ ] **Documentation updates:** draft a Sphinx how-to covering heuristic configuration presets, registry usage, and interpreting the new benchmarking metrics.

##### Plan – Documentation Updates (Heuristics & Benchmarks)
- [ ] Draft a comprehensive how-to for heuristic configuration.
  * Outline preset usage (`--operator-preset`, merging rules) and provide practical examples.
  * Explain how to combine presets with explicit `--operator` / `--operator-weight` overrides.
  * Highlight registry-driven operators, noting advanced neighbourhoods and opt-in features (parallel multistart, batched evaluation, ILS/Tabu).
- [ ] Add benchmark interpretation guidance.
  * Describe the meaning of comparison columns (solver category, objective gaps, runtime ratios) with textual examples.
  * Reference the generated plots in `docs/_static/benchmarks/` and explain how to produce fresh charts.
  * Link telemetry logging and comparison metrics to the hyperparameter tuning roadmap.
- [ ] Document CLI touchpoints and cross-links.
  * Update CLI reference (`docs/reference/cli.rst`) with a dedicated section on heuristics presets and comparison flags (`--include-ils`, `--include-tabu`, plotting helper).
  * Ensure top-level roadmap/docs reference the new how-to and plotting utilities.
- [ ] Add regression scaffolding for docs content.
  * Extend doc build/checklist notes to regenerate plots when benchmarks change.
  * note TODO for future automation (maybe script to refresh benchmarking figures).

###### Subtasks – Heuristic How-to Draft
- [ ] Create `docs/howto/heuristic_presets.rst` (or similar) with structure:
  * Introduction mapping presets to use-cases.
  * CLI examples combining presets, weights, and parallel knobs.
  * Registry/operator overview (swap/move/block insertion/cross exchange/mobilisation shake) with brief behaviour summaries.
  * Optional section on ILS/Tabu integration, referencing their respective how-tos.
- [ ] Include cross-references to existing docs (CLI reference, telemetry, parallel execution how-to).
- [ ] Add a “next steps” link pointing readers to benchmarking guidance and tuning notes.

###### Subtasks – Benchmark Interpretation Section
- [ ] Update `docs/howto/benchmarks.rst` to add a walkthrough of comparison metrics.
  * Provide table snippet highlighting key columns.
  * Explain the plots and how to interpret negative/positive gaps.
  * Mention multi-solver CLI invocation to generate the richer summary.
- [ ] Ensure the plots appear in the Sphinx build (responsive layout, alt-text) and note the script usage.

###### Subtasks – CLI Reference Refresh
- [ ] Expand `docs/reference/cli.rst` heuristics section with:
  * Preset overview and merging behaviour.
  * Flags for enabling advanced operators, multi-start, batching, ILS/Tabu.
  * Pointer to the new how-to and plotting script.
- [ ] Verify cross-links (toctree, references) resolve correctly after the new pages are added.

###### Subtasks – Maintenance Notes / Automation Hooks
- [ ] Document in `notes/metaheuristic_hyperparam_tuning.md` or README how to regenerate plots when telemetry changes.
- [ ] Add a lightweight checklist entry (maybe in `docs/howto/benchmarks.rst` “Maintaining this page”) reminding contributors to rerun `scripts/render_benchmark_plots.py` after major benchmark updates.

##### Plan – ILS / Hybrid Solver
- [x] Algorithm design: outline ILS move phases, perturbation strategy, and hybridisation with MIP warm starts.
- [x] Implementation: create `solve_ils` (or `solve_hybrid`) module, integrating with operator registry and optional MIP kickoffs.
- [x] Testing & benchmarks: add unit/integration coverage, compare SA vs ILS/Hybrid on benchmarks, and capture telemetry.
- [x] Documentation: update CLI reference/how-to notes and roadmap findings.

###### Subtasks – ILS/Hybrid Algorithm Design
- [x] Select base phases: greedy start → local search (swap/move/block insertion) → perturbation (e.g., multi-start or random block swap).
  * Phase 0: warm start via `_init_greedy` (same as SA), optionally seeded from MIP solution when available.
  * Phase 1: apply local search using registry operators with batch sampling (reuse `_neighbors`, `_evaluate_candidates`).
  * Phase 2: perturbation step (e.g., random multi-block swap or short SA run) before re-entering local search; expose intensity parameter.
- [x] Define restart/acceptance criteria (e.g., accept improved solution or probabilistic acceptance if objective within threshold).
  * Acceptance: adopt new solution if it improves the best objective or clears diversification threshold (objective >= current - epsilon).
  * Restart trigger: after `stall_limit` perturbations without improvement, restart from best-known solution with fresh perturbation intensity.
  * Track metrics for telemetry (`perturbations`, `restarts`, `acceptance_delta`).
- [x] For hybrid path, specify when to invoke MIP warm start (e.g., after fixed iterations or when stalls > limit) and how to import assignments back.
  * Invoke `solve_mip` (time-boxed) after initial ILS cycles or when stalls exceed limit; use its assignments as new baseline if feasible.
  * Convert MIP assignments into schedule plan for ILS (shared helper) and reset tabu/ILS state accordingly.
  * Guard with opt-in flag (`--hybrid-use-mip`); fall back gracefully if MIP fails/timeouts.

###### Subtasks – ILS/Hybrid Implementation
- [x] Implement solver function (`solve_ils` or `solve_hybrid`) leveraging shared registry/operators; expose batch/parallel knobs similar to SA.
- [x] Add CLI command (`fhops solve-ils`) with options for iterations, perturbation strength, restart policy, and optional MIP warm start configuration.
- [x] Extend benchmarking harness to optionally include the new solver (`--include-ils`), writing telemetry comparable to SA/Tabu.

###### Subtasks – Testing & Benchmarks (ILS/Hybrid)
- [x] Unit tests covering perturbation behaviour, restart logic, and feasibility checks.
- [x] Regression tests on minitoy scenario ensuring feasibility and consistent objective. *(`pytest tests/test_regression_integration.py`)* 
- [x] Benchmark runs (minitoy/med42/large84) comparing SA, Tabu, and ILS/Hybrid; record telemetry/decision notes. *(See `tmp/bench_ils/summary.{csv,json}` — SA remains strongest on all scenarios; ILS trails SA but beats Tabu on quality while staying sub-second on minitoy/med42.)*

###### Subtasks – Documentation (ILS/Hybrid)
- [x] Update CLI reference and telemetry docs with new solver options/fields.
- [x] Add how-to section demonstrating ILS/Hybrid usage, configuration defaults, and comparative results.
- [x] Summarise findings in roadmap/changelog, noting default recommendation (opt-in vs default).

##### Plan – Benchmark Reporting Enhancements
- [x] Extend benchmark summaries with solver comparison deltas (SA vs ILS vs Tabu vs MIP) and highlight the top-performing heuristic per scenario.
  * Calculate absolute/relative gaps for each heuristic against MIP (where available) and between heuristics when MIP is skipped. *(New columns `objective_gap_vs_best_heuristic` and `runtime_ratio_vs_best_heuristic` complement the existing MIP gap/ratio fields.)*
  * Include summary rows/columns in `summary.csv/json` to surface best objective, runtime, and heuristic category. *(Added `solver_category`, `best_heuristic_solver`, `best_heuristic_objective`, `best_heuristic_runtime_s`.)*
  * Ensure telemetry logs capture solver labels consistently so downstream analysis scripts can operate on the richer data. *(Telemetry entries already carry ``solver`` for each record, so no schema change required.)*
- [x] Generate visual artefacts (tables/plots) for docs.
  * Add a small pandas/matplotlib helper under `scripts/` to render bar charts for objective gaps and runtime ratios. *(`scripts/render_benchmark_plots.py` generates the figures from a suite summary.)*
  * Store generated SVG/PNG outputs in `docs/_static/benchmarks/` and reference them from the benchmarking how-to. *(Plots `objective_gap_vs_best_heuristic.png` and `runtime_ratio_vs_best_heuristic.png` now ship and are linked in `docs/howto/benchmarks.rst`.)*
- [x] Update Sphinx content to explain the new metrics and visuals.
  * Refresh `docs/howto/benchmarks.rst` with interpretation guidance for the comparison columns and plots. *(Added “Visual Comparisons” section with references to generated figures and instructions.)*
  * Add a short narrative in `docs/reference/cli.rst` (bench section) describing how to enable multi-solver comparisons and where to find the artefacts. *(CLI reference now calls out the combined `--include-ils/--include-tabu` mode and comparison columns.)*
- [x] Add regression tests/fixtures to lock in the enhanced reporting.
  * Extend `tests/test_benchmark_harness.py` to assert that comparison fields appear when multiple solvers are included. *(Tests cover SA+MIP, SA+Tabu, and preset comparison paths.)*
  * Include a fixture with predetermined solver metrics to keep the comparison calculations stable across refactors. *(Existing minitoy fixture continues to anchor numeric expectations; no new fixture needed at this stage.)*

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
- [x] **Design & interfaces:** define new operators (block insertion, cross-machine exchange, mobilisation-aware shake), specifying preconditions, behaviour, and additional context needed (e.g., distance lookups).
- [x] **Implementation:** add operator classes that reuse the shared sanitizer, register them with default weights, and ensure plan cloning stays efficient.
- [x] **Weighting & presets:** set sensible defaults, expose new presets (e.g., `explore`, `mobilisation`), and update CLI docs/config helpers.
- [x] **Benchmark evaluation:** compare baseline vs. extended operator sets across minitoy/med42/large84, capturing telemetry and summarising outcomes in notes/changelog. *(Raised default MIP timeout to 1800 s so large84 runs complete without manual overrides.)*
- [x] **Testing & regression:** expand unit/regression coverage to exercise new operators (window constraints, mobilisation penalties, lock handling).

#### Parallelisation ideas (sidebar)
- Spin up multi-start SA runs in parallel with different seeds/presets; keep the best objective (embarrassingly parallel).
- Evaluate a batch of neighbours concurrently (spawn workers to score candidates, accept the best improvement).
- Parallelise preset/parameter sweeps (cooling rates, weight mixes) using joblib/multiprocessing to exploit cores.
- Run per-core SA instances that emit telemetry to a shared JSONL log; post-process to select or blend results.

##### Plan – SA Parallel Execution (opt-in)
- [x] Multi-start orchestration: run multiple SA instances in parallel (distinct seeds/presets) and aggregate the best objective.
- [x] Batched neighbour evaluation: extend `_neighbors` to propose/evaluate batches concurrently via worker pool.
- [x] CLI/config integration: add flags to toggle parallel runs, set worker counts, and expose telemetry about parallel paths.
- [x] Testing & benchmarks: validate reproducibility, ensure opt-in paths fall back cleanly, and benchmark speed/quality trade-offs.

###### Subtasks – Multi-start orchestration
- [x] Design a controller that spawns `n` independent SA runs (multiprocessing/joblib) and returns the best result plus per-run telemetry.
  * Define `fhops.optimization.heuristics.multistart.run_multi_start(pb, seeds, presets, max_workers)` returning `(best_result, runs_meta)`.
  * Use `concurrent.futures.ProcessPoolExecutor` with joblib-style fallback; ensure graceful shutdown and timeout handling.
  * Gather each run's telemetry (`meta` payload) and compute best objective deterministically; retain full logs for debugging.
- [x] Add per-run seed/preset exploration strategy (e.g., stratified presets) and document recommended defaults.
  * Generate deterministic seed grid (e.g., `base_seed + i*1000`) and map presets cyclically (`['default','explore','mobilisation','stabilise']`).
  * Allow custom strategies via callables (user can supply preset list/seed generator); provide helper `build_exploration_plan(n, presets=None)`.
  * Document recommended defaults in roadmap/docs and note telemetry fields to capture chosen seed/preset per run.
- [x] Ensure shared telemetry logging (JSONL) de-duplicates entries and captures the selected best run metadata.
  * Extend telemetry writer to accept `run_id`/`preset_label` fields; guard against duplicate entries via hash/set.
  * After multi-start aggregation, append a summary record (`best_run_id`, `best_objective`, `runs_executed`) to the same log.
  * Add CLI flag to route per-run logs to separate directory when desired (e.g., `--multi-start-log-dir`).

- [x] Profile memory/CPU usage to confirm batch evaluation scales without overwhelming system resources.
  * Benchmarked minitoy/med42 (`iters=500`) and minitoy/med42/large84 (`iters=2000`) across `batch_size` in {None,4} and `max_workers` in {None,4}; CSVs stored at `tmp/sa_batch_profile.csv` and `tmp/sa_batch_profile_long.csv`.
  * Threaded evaluation consistently added 5–6x overhead without objective gains; recommend keeping `max_workers=None` as default and adding guardrails to fall back automatically when parallel speedup is not observed.

###### Subtasks – CLI/config integration (parallel)
- [x] Add CLI options (`--parallel-multistart`, `--parallel-workers`, `--batch-neighbours`) with safe defaults disabled.
- [x] Update docs/telemetry to include parallel configuration metadata and per-run stats.
- [x] Provide guardrails to fall back to single-thread mode on failure (exception handling, warnings).

###### Subtasks – Testing & benchmarks (parallel)
- [x] Add unit/integration tests verifying identical results when `workers=1` (parity with single-thread path). *(See `tests/heuristics/test_sa_batch.py::test_solve_sa_batch_matches_single`.)*
- [x] Benchmark minitoy/med42/large84 with parallel options (record speedups/objective differences). *(Profiles captured in `tmp/sa_batch_profile.csv` and `tmp/sa_batch_profile_long.csv`.)*
- [x] Document findings in roadmap/changelog and decide on default stance after evaluation. *(Threaded evaluation shows 5–6× overhead, so defaults remain sequential with parallel options opt-in.)*

##### Plan – Advanced neighbourhoods: Design & interfaces
- [x] Catalogue candidate operators with design goals:
  * [x] **BlockInsertionOperator** — relocate an unlocked block to an alternate feasible shift (same machine or compatible peer) to reduce congestion, unlock blackout conflicts, or align with mobilisation cooldowns.
  * [x] **CrossExchangeOperator** — exchange two assignments between machines/shifts when each machine can service the other block, targeting workload balance and freeing future sequencing options.
  * [x] **MobilisationShakeOperator** — orchestrate a controlled mobilisation-heavy move that explores distant shifts while keeping cooldowns and landing capacities within configured slack.
- [x] For each operator, specify detailed constraints and telemetry:
  * [x] **BlockInsertionOperator**
    - Preconditions: source block not locked; candidate target machine supports block role; shift lies within block window; landing slot available; mobilisation cooldown for target machine satisfied.
    - Inputs: `distance_lookup[(machine_id, block_id)]`, `block_windows[block_id]` (list of `(shift_id, machine_id)` windows), machine availability matrix, landing capacity map by `(landing_id, shift_id)`, mobilisation cooldown ledger, blackout map.
    - Schedule deltas: remove `(machine_src, shift_src)` assignment; insert `(machine_tgt, shift_tgt)` assignment; optionally mark source shift idle placeholder to preserve horizon; recompute mobilisation chain for `machine_src` and `machine_tgt`.
    - Telemetry: `distance_delta`, `shift_offset` (target shift index minus source), `machine_changed` flag, `landing_feasible` boolean.
  * [x] **CrossExchangeOperator**
    - Preconditions: both blocks unlocked; machines mutually capable for swapped roles; candidate shifts within respective windows; landing constraints satisfied post-swap; mobilisation cooldowns satisfied for both machines.
    - Inputs: compatibility matrix (machine ↔ block role), `distance_lookup`, both blocks' windows, landing capacity map for both landings, mobilisation cooldown ledger, blackout map.
    - Schedule deltas: replace `(machine_a, shift_a)` with block_b and `(machine_b, shift_b)` with block_a; update mobilisation sequences for both machines; ensure vacated shifts re-evaluated for availability.
    - Telemetry: `distance_delta_a`, `distance_delta_b`, `workload_delta` (difference in assigned hours across machines), `swap_success` boolean.
  * [x] **MobilisationShakeOperator**
    - Preconditions: block unlocked; machine has mobilisation slack budget remaining; neighbouring shifts available for temporary vacancy; alternative landing within `shake_radius`; mobilisation cooldown for candidate machine satisfied post-move.
    - Inputs: mobilisation distance matrix, `mobilisation_budget[machine_id]`, blackout windows, landing capacity forecast, optional rejection counter per block to avoid repeated failures.
    - Schedule deltas: vacate existing assignment; assign block to distant `(machine_tgt, shift_tgt)`; optionally insert idle placeholder in source to maintain coverage; recalc mobilisation path for involved machines.
    - Telemetry: `mobilisation_delta`, `cooldown_triggered`, `shake_depth` (number of shifts moved), `acceptance_temperature`.
- [x] Extend `OperatorContext` with optional references: `distance_lookup`, `block_windows`, `landing_capacity`, `mobilisation_budget`, `cooldown_tracker`. Defaults remain `None`; populated in SA driver via cached evaluator outputs so operators share consistent data without recomputation.
- [x] Draft pseudo-code for each operator capturing candidate selection, validation order, and fallback behaviour (return `None` when infeasible):
  * **BlockInsertionOperator**
    ```python
    def apply(ctx: OperatorContext) -> Schedule | None:
        block = ctx.rng.choice(ctx.schedule.unlocked_blocks())
        candidates = feasible_insertions(block, ctx)
        for machine_id, shift_id in shuffle(candidates, ctx.rng):
            if not mobilisation_ok(machine_id, shift_id, block, ctx):
                continue
            candidate = ctx.schedule.clone()
            candidate.move_block(block, machine_id, shift_id)
            if ctx.sanitizer(candidate):
                ctx.telemetry.record("block_insertion", block, machine_id, shift_id)
                return candidate
        return None
    ```
  * **CrossExchangeOperator**
    ```python
    def apply(ctx: OperatorContext) -> Schedule | None:
        pair = pick_exchange_pair(ctx.schedule, ctx.rng)
        if pair is None:
            return None
        a, b = pair  # (machine_id, shift_id, block_id)
        if not exchange_feasible(a, b, ctx):
            return None
        candidate = ctx.schedule.clone()
        candidate.swap_assignments(a, b)
        return candidate if ctx.sanitizer(candidate) else None
    ```
  * **MobilisationShakeOperator**
    ```python
    def apply(ctx: OperatorContext) -> Schedule | None:
        block = select_stagnant_block(ctx.schedule, ctx.telemetry, ctx.rng)
        target = pick_mobilisation_target(block, ctx)
        if target is None:
            return None
        candidate = ctx.schedule.clone()
        candidate.reassign(block, *target)
        if mobilisation_within_budget(candidate, ctx):
            return candidate if ctx.sanitizer(candidate) else None
        return None
    ```

##### Plan – Advanced neighbourhoods: Implementation
- [x] Implement operator classes aligned with the design spec.
  * [x] `BlockInsertionOperator` (respecting windows, cooldowns, landing caps).
  * [x] `CrossExchangeOperator` (machine compatibility, dual mobilisation checks).
  * [x] `MobilisationShakeOperator` (budget-aware diversification move).
- [x] Refactor shared helper utilities so plan cloning/sanitizer application is consistent across operators.
- [x] Register the new operators in `OperatorRegistry.from_defaults()` with guarded default weights (initially 0.0 for experimental moves).
- [x] Update preset definitions to include the new operators where appropriate (`explore`, `mobilisation`, etc.).

##### Plan – Advanced neighbourhoods: Weighting & presets
- [x] Design new presets (`explore`, `mobilisation`, etc.) combining existing and new operators with documented rationale.
  * [x] `explore`: swap 1.0, move 1.0, block_insertion 0.6, cross_exchange 0.6, mobilisation_shake 0.2 (balanced diversification for general improvements).
  * [x] `mobilisation`: swap 0.8, move 0.8, block_insertion 0.4, cross_exchange 0.4, mobilisation_shake 1.2 (aggressively explores mobilisation-heavy moves).
  * [x] `stabilise`: swap 0.5, move 1.5, block_insertion 0.2, cross_exchange 0.2, mobilisation_shake 0.0 (focus on consolidation/minimal mobilisation).
- [x] Allow CLI overrides to combine presets with explicit weights; ensure `--list-operator-presets` reflects new options.
- [x] Document default weights and recommended use cases (e.g., mobilisation-heavy scenarios). *(docs/reference/cli.rst updated to enumerate presets and note explore/mobilisation/stabilise guidance.)*

##### Plan – Advanced neighbourhoods: Benchmark evaluation
- [x] Extend benchmark harness to compare baseline vs. preset configurations; log objective, runtime, and operator stats.
  * [x] Add CLI flags (e.g., `--preset-comparison`) to run multiple presets sequentially.
  * [x] Update benchmark summary output to include preset name, operator weights, and acceptance stats.
  * [x] Ensure JSONL telemetry captures preset context for downstream analysis.
- [x] Analyse telemetry JSONL to quantify improvements/changes; summarise findings in notes and changelog entries.
  * [x] Collect benchmark runs with `--compare-preset` (default vs explore/mobilisation/stabilise) across sample scenarios. *(`fhops bench suite --sa-iters 1000` on minitoy and med42; med42 run skipped MIP via `--no-include-mip` to keep runtime manageable.)*
  * [x] Parse summary/telemetry outputs to extract objective gaps, runtime changes, and operator acceptance stats. *(Default vs explore/mobilisation reduced objective gap on minitoy from 41 → 22, med42 objective improved from -677 → -268 while runtime grew ~4×; acceptance remained 1.0 for all operators given current sanitizer behaviour.)*
  * [x] Summarise findings in this document and note any recommended default adjustments; update changelog if changes warranted. *(Advanced presets offer better objective quality at higher runtime—recommend keeping default weights as-is, treating `explore`/`mobilisation` as opt-in for diversification. No changelog update beyond benchmark tooling entry.)*
- [x] Decide on default inclusion of new operators based on benchmark evidence. *(Keep current default swap/move weights: diversification presets improve objective quality but add 2–4× runtime on minitoy/med42; retain opt-in presets until further tuning or adaptive switching is available.)*

##### Plan – Advanced neighbourhoods: Testing & regression
- [x] Add unit tests verifying each operator respects availability, windows, locks, and mobilisation rules. *(Implemented in `tests/heuristics/test_operators.py` covering window constraints, machine capability filters, schedule locks, and mobilisation spacing.)*
- [x] Update regression fixtures (e.g., mobilisation-heavy scenario) to ensure new operators improve or at least maintain objective. *(Regression integration test exercises explore/mobilisation/stabilise presets and asserts objectives remain at or above the baseline value.)*
- [x] Seed RNG deterministically so regression benchmarks remain reproducible. *(SA now instantiates a local RNG per solve, leaving global state untouched for other tests.)*
- [x] **Tabu Search prototype:** implement a Tabu neighbourhood on top of the registry (tabu tenure, aspiration criteria) and compare results against SA in the benchmarking harness. Decide whether to expose as `fhops solve-tabu`.

##### Plan – Tabu Search Prototype
- [x] Algorithm design: define neighbourhood moves, tabu tenure strategy, aspiration criteria, and scoring alignment with SA.
- [x] Implementation: build `fhops.optimization.heuristics.tabu` module (builder, solver entrypoint, CLI integration).
- [x] Testing & benchmarks: unit tests for tabu mechanics, regression comparison against SA, benchmarking on sample scenarios. *(Tabu remains opt-in after comparing against SA on minitoy/med42/large84.)*
- [x] Documentation: CLI documentation, roadmap updates, and how-to section for configuring Tabu Search.

###### Subtasks – Tabu Algorithm Design
- [x] Select base neighbourhoods (reuse swap/move/block insertion) and define Tabu structures (e.g., move-based tabu list).
  * Use existing `SwapOperator`, `MoveOperator`, and `BlockInsertionOperator` as candidate generators; limit batch size via registry weights for diversity.
  * Track tabu entries as tuples `(machine_id, from_block, to_block, day, shift)`; maintain a FIFO queue plus hash for O(1) lookups.
  * Support optional short-term tabu for block-machine assignments to prevent immediate reversals.
- [x] Specify tabu tenure (fixed vs adaptive), aspiration criteria, and tie-breaking when aspiration triggers.
  * Start with fixed tenure = `max(10, len(machines))`; expose CLI parameter for overrides.
  * Aspiration: allow tabu move if objective improves on best-known solution or satisfies diversification threshold (e.g., mobilisation slack reduction).
  * When multiple candidates pass aspiration, prefer highest objective gain, then lowest mobilisation cost.
- [x] Align objective scoring with shift-aware mobilisation objective and determine stopping conditions (iterations, non-improving stalls).
  * Reuse `_evaluate` from SA to keep objective parity; store best solution and non-improving counter.
  * Default stopping: `iters` iterations or `stall_limit` (e.g., 200 iterations without improvement); expose CLI flag for stall limit.
  * Ensure tabu run emits telemetry comparable to SA (objective, stalls, tenure, aspiration hits).

###### Subtasks – Tabu Implementation
- [x] Create `tabu.py` with solver function (`solve_tabu`) leveraging registry operators and tabu structures.
- [x] Add CLI entry (`fhops solve-tabu`) with options for tenure, aspiration, iterations, and telemetry logging.
- [x] Ensure integration with benchmarking harness (`fhops bench suite`) to compare against SA. *(Use `--include-tabu` to emit Tabu rows in summaries.)*

###### Subtasks – Testing & Benchmarks (Tabu)
- [x] Unit tests covering tabu list behaviour, aspiration, and feasibility checks.
- [x] Regression tests ensuring baseline objective matches expectations on minitoy scenario.
- [x] Benchmark runs (minitoy/med42/large84) comparing SA vs Tabu; capture telemetry for roadmap notes. *(Results in `tmp/tabu_bench/summary.csv` show Tabu worse than SA across scenarios; keep solver experimental.)*

###### Subtasks – Documentation (Tabu)
- [x] Update CLI reference and telemetry docs with Tabu-specific fields/options.
- [x] Add a how-to page describing Tabu configuration, example runs, and when to prefer it over SA.
- [x] Note findings in roadmap/changelog once evaluation complete.
