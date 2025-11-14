Metaheuristic Hyperparameter Tuning Plan
========================================

Date: 2025-11-11  
Status: Draft — bootstrapping telemetry-backed tuning loops for SA/ILS/Tabu.

## Objectives
- Capture rich telemetry from heuristic runs (config, interim metrics, outcomes).
- Provide conventional tuning drivers (grid/random/Bayesian) that operate on the telemetry store.
- Explore an LLM-assisted agent loop that consumes telemetry and proposes new presets with guardrails.
- Document workflows (CLI, docs) so users can reproduce sweeps and compare tuners.

## Deliverables Checklist

### Telemetry & Persistence Groundwork
- [x] Define telemetry schema (`TelemetryRun`, `TelemetryStep`) covering scenario, solver, seeds, operator weights, acceptance stats, objective trajectory, timing.
- [x] Implement logging hooks in SA/ILS/Tabu solvers and playback validators writing to JSONL (phase 1) and SQLite (optional phase 2).
  - [x] Simulated Annealing JSONL prototype: run + step telemetry recorded via `RunTelemetryLogger`.
  - [x] ILS JSONL logging (run + step snapshots, CLI integration).
  - [x] Tabu JSONL logging (run + step snapshots, CLI integration).
  - [x] Playback telemetry logging (CLI hook + step logs).
- [x] Provide helper module (`fhops.telemetry.run_logger`) with append/query utilities and retention controls.
- [x] Introduced SQLite persistence helper (`fhops.telemetry.sqlite_store.persist_run`) to mirror run metrics/KPIs alongside the JSONL stream.
- [x] Document retention/rotation strategy and storage location in this note + CLI help.
- [x] Introduce scenario descriptor capture (block/machine counts, horizon, landing stats) so tuners can learn across instances.
- [x] Add schema versioning to run/step records and document the schema contract to de-risk future consumers.
- [x] Persist KPI outcomes / objective components in a normalised telemetry table (SQLite phase) for ML feature pipelines.

### Conventional Tuning Toolkit
- [x] Implement grid and random search drivers operating on the telemetry store (CLI-friendly).
- [x] Grid tuner execution mode (`fhops tune-grid`) evaluating preset/batch-size cartesian products with telemetry logging.
- [x] Random tuner execution mode (`fhops tune-random`) running SA sweeps and recording telemetry.
- [x] CLI tuners (random/grid/bayes) append `tuner_summary` records capturing per-scenario best objectives and configuration counts for quick comparisons.
- [x] `fhops telemetry report` command summarises tuner performance to CSV/Markdown directly from the SQLite store (see tests and telemetry docs).
- [x] Integrate a Bayesian/SMBO tuner (Optuna TPE) with pluggable search spaces (`fhops tune-bayes`).
- [x] Expose CLI commands (`fhops tune random`, `fhops tune bayes`) that schedule sweeps over scenario bundles.
- [x] Generate automated comparison reports (CSV/Markdown) summarising best configs per scenario tier; stash fixtures/tests.
- [ ] Benchmark grid vs. random vs. Bayesian/SMBO (and future neural/meta-learned) tuners across canonical scenarios; log comparative telemetry (win rate, best obj delta, runtime).
  - [x] Finalise `benchmark_bundle_plan` (baseline bundle + synthetic tiers) with aligned budgets per tuner and document the configuration in this note and `docs/howto/telemetry_tuning.rst`.
  - [ ] Automate comparison artefacts integration in CI (publish `tuner_comparison.*` and `tuner_leaderboard.*` alongside summaries).
  - [x] Produce per-bundle leaderboards/comparisons (baseline vs each synthetic tier) and publish them alongside global summaries.
  - [ ] Add budget sensitivity sweeps (e.g., 100/250/500 iterations) and chart marginal gain vs runtime.
    - [ ] When running local sweeps, target ≥64 CPU cores (leave ~8 cores idle) and cap per-run RSS to ~8 GB so multi-core runs remain stable.
  - [x] Incorporate ILS/Tabu (and future tuners) into the benchmark harness with aligned budgets.
- [ ] Generate convergence diagnostics by comparing heuristic best trajectories against MIP optimal objectives; record convergence slopes and thresholds.
  - [ ] Measure iterations-to-≤1% optimality gap per tuner/scenario when MIP optima are known.
  - [ ] Fit convergence models (gap vs. iterations vs. scenario features/difficulty) and store parameters for future stopping-criterion recommendations.
  - [ ] Extend benchmark plans with long-budget runs (e.g., 100/250/500+ iters or trials) to populate the convergence dataset.
- [ ] Compute scenario difficulty indices (delta to MIP optimum, tuner win distribution) and include in comparison artefacts.
- [x] Schedule medium/long tier convergence sweeps (baseline + synthetic bundles) with MIP baselines and publish resulting convergence summaries to docs/Pages once complete.
  - Baseline convergence dataset: `tmp/convergence-baseline/` (telemetry, history, convergence summaries).
  - Synthetic convergence dataset: `tmp/convergence-synthetic/` (telemetry, history, convergence summaries).
  - Long-tier Tabu runs limited to 3 restarts × 2 000 iterations to stay within wall-clock bounds; revisit with parallel workers enabled if additional samples are required.
  - Convergence summaries currently empty because MIP baselines are missing from the telemetry store; next sweep iteration must include `solve-mip` runs (or replay archived results) before recomputing convergence metrics.

### Convergence modelling experiment (draft outline)

1. **Populate baselines**
   - Ensure each scenario participating in convergence analysis has an up-to-date MIP optimum recorded in the telemetry store (`runs` table with `solver='mip'`).
   - If solving the full MIP is infeasible, capture best-known upper bounds and record them as reference metrics with an explicit `status`.
2. **Feature extraction**
   - From convergence runs: iterations to ≤1 % gap (from `convergence_runs.csv`), final best objective, acceptance statistics (mean acceptance rate, number of improvements), tier label, tuner algorithm.
   - Scenario descriptors: machines, blocks, horizon (already emitted in telemetry `context.scenario_features`).
   - MIP metadata: objective value, solve time, termination condition.
3. **Modelling plan**
   - Start with non-parametric regression (LOESS or scikit-learn `RandomForestRegressor`) to map `(scenario_features, tier, algorithm, budget)` → `iterations_to_1pct`.
   - Build per-algorithm parametric fits (e.g., power-law `gap(t) = a * t^{-b}`) to derive interpretable slopes for documentation.
   - Validate via time-based train/test split (e.g., baseline scenarios for training, synthetic for hold-out) and measure MAE on predicted iterations.
4. **Outputs**
   - Generate Markdown/CSV summaries: recommended iteration budget per tier & algorithm for new scenarios (based on regression predictions + safety margin).
   - Visualise convergence curves (Altair) overlaying empirical and fitted models.
5. **Automation**
 - Extend `scripts/analyze_tuner_reports.py` or add a companion script (`scripts/fit_convergence_models.py`) to reproducibly generate the models.
 - Store fitted parameters/artefacts under `docs/examples/analytics/data/convergence/`.

### Documentation TODOs (post-modelling)
- Publish convergence datasets and model recommendations in the telemetry how-to once baselines are populated and fits are available.
- Add summary section to the README linking to convergence reports and recommended iteration budgets.
- Document dual convergence thresholds (hard=≤1%, soft=≤5%) in docs and CLI help once analytics incorporate both signals.

### Dual-threshold convergence analysis (new)
- [x] Update convergence reporting to emit both hard (≤1%) and soft (≤5%) gap metrics per run/tier so we can observe early “soft” convergence and final “hard” convergence.
- [x] Extend `convergence_summary` outputs with counts/iteration statistics for each threshold (e.g., `success_rate_soft`, `mean_iterations_to_5pct`) to capture curvature information.
- [ ] Plot convergence trajectories highlighting when runs cross 5% vs. 1% to visualise rate and curvature for each tuner.
- [ ] Feed both thresholds into the modelling experiment (fit separate regressors and/or joint models) to improve automated stopping rules.

### Parallel telemetry sweeps (planned upgrade)
- [x] Add process-level parallelism to `scripts/run_tuning_benchmarks.py` (target 16 worker processes × 4 threads each) so scenario/tier/tuner jobs run concurrently.
  - [x] Introduce a `--max-workers` flag and use `ProcessPoolExecutor` to dispatch `(scenario, tuner, tier)` units, buffering CLI commands per worker.
  - [x] Ensure each worker writes telemetry to a unique chunk (`runs.<worker>.jsonl`, per-run step logs, SQLite copy).
- [x] Implement a deterministic merge step that consolidates JSONL, step logs, and SQLite entries after worker completion (dedupe on `run_id`).
  - [ ] Add automated tests that run two worker chunks and verify the merged telemetry matches serial execution.
- [ ] Increase default heuristic parallelism (e.g., `--parallel-workers` 4) when `--max-workers` is set so each worker leverages multi-core hardware without oversubscription.
- [ ] Update docs (`docs/howto/telemetry_tuning.rst`) with recommended parallel flags, resource guidance (16 proc × 4 threads), and troubleshooting tips.
- [ ] Schedule medium/long tier convergence sweeps (baseline + synthetic bundles) with MIP baselines and publish resulting convergence summaries to docs/Pages once complete.
- [x] Emit tuner-level meta-telemetry (algorithm name, configuration, budget, convergence stats) so higher-level orchestration can evaluate tuner performance.
- [x] Extend `RunTelemetryLogger` / CLI tuners to include `tuner_meta` (algorithm label, search budget, config search space hints, convergence indicators).
  - [x] Persist meta fields in SQLite (either JSON column or dedicated table) for downstream selection agents.
  - [x] Update docs/tests to cover meta-telemetry schema, ensuring backwards compatibility for existing consumers.
- [x] Fold the heuristic parameter catalogue into user-facing docs (`docs/howto/telemetry_tuning.rst`, CLI help) so the tuning surface is documented alongside execution workflows.
- [x] Introduce a tractable `small21` baseline dataset (≈½ the scale of `med42`) so MIP solves finish quickly and provide a second reference optimum; wire it into the convergence sweeps and telemetry fixtures.
- [x] Schedule an extended MIP benchmarking window (overnight/off-peak) to finish the outstanding `med42` optimum and capture long-run solver telemetry once resource constraints ease.
- [x] Wire in Gurobi as an optional MIP backend (CLI flag + docs); keep HiGHS as default but document licensing/install steps so we can solve larger baselines reliably.
- [x] Run long-leash convergence experiments for each heuristic (SA/ILS/Tabu) on representative scenarios (minitoy, small21, med42, synthetic tiers) with budgets in the 2 000–10 000+ iteration range; capture wall-clock vs. improvement curves and record when 5 % / 1 % gaps are actually met.
  - Telemetry + step logs live in `tmp/convergence-long/` (see `long_run_summary.csv` for wallclock-per-1000 iteration stats and gap checkpoints).
  - SA/ILS hit ≤5 % gap only on `synthetic-medium` within 10 000 iterations (SA ≈100 iters, ILS ≈225); other scenarios remain >10 % off, suggesting we need larger horizons or richer neighbourhoods.
- Tabu completes 10 000 iterations in milliseconds but stalls >20 % gap even on synthetic sets — revisit operator mix/tabu tenure before counting it as converged.
- Convergence reports now expose both absolute gap (`ΔZ = Z* – Zrun`) and range-normalised gap (`(Z* – Zrun)/(Z* – Zbaseline)`) so negative objectives don’t distort percentages.
- [ ] Extend SA/ILS sweeps to ≥25 000 iterations (or ≥10 minute wall-clock, whichever is larger) on `med42`, `small21`, and all synthetic tiers so the trajectories mirror the MIP solve-time budgets.
  - Use the measured wall-clock per 1 000 iterations from `long_run_summary.csv` to set target horizons (e.g., med42 SA ≈2.5 s/1k ⇒ 240 k iterations for a 10 min leash, 360 k+ if matching a 15 min Gurobi solve).
  - Capture per-minute checkpoints (iteration, best objective, wall-clock) to drive Z* vs. iteration/time plots.
- [ ] Re-tune Tabu tenure/operator weights under long budgets (≥10 minutes) and log whether diversification closes the >20 % gap; fall back to hybrid or multi-neighbour scoring if not.
- [ ] Fit scenario-size vs. iterations-to-gap curves (5 % / 1 %) using the long-run telemetry to inform adaptive stopping heuristics. Candidate predictors: block count, machine count, planning horizon days, MIP solve time, difficulty proxies (e.g., mobilisation density).
- [ ] Surface Z* trajectories (iteration + wall-clock) per scenario/heuristic in the docs so we can eyeball convergence shapes before training meta-models.

## Benchmark Bundle Plan (draft)

### Budget tiers (wired into `run_tuning_benchmarks.py`)

| Tier label | Random tuner budget | Grid tuner budget | Bayesian/SMBO budget |
|------------|--------------------|-------------------|----------------------|
| `short`    | 2 runs × 150 iters | presets `balanced`,`explore` × batch `{1,2}` × 150 iters | 20 trials × 150 iters |
| `medium`   | 3 runs × 300 iters | presets `balanced`,`explore` × batch `{1,2}` × 300 iters | 40 trials × 300 iters |
| `long`     | 5 runs × 600 iters | presets `balanced`,`explore` × batch `{1,2}` × 600 iters | 75 trials × 600 iters |

Smaller smoke runs override the tier defaults via plan-specific budgets (see table below), but the CLI runner now accepts `--tier short --tier medium --tier long` and stamps telemetry with `context.tier`.

| Plan name       | Bundles / Scenarios                                        | Default tiers | Notes |
|-----------------|------------------------------------------------------------|---------------|-------|
| baseline-smoke  | `baseline` (examples/minitoy, examples/med42)              | `short`       | Overrides short tier to 3 runs × 250 iters and 30 SMBO trials to mirror legacy smoke timings. |
| synthetic-smoke | `synthetic` (small, medium, large tiers)                   | `short`       | Short tier lifted to 300 iters / 30 trials to exercise the synthetic instances. |
| full-spectrum   | baseline + synthetic bundles (combined run)               | `short`,`medium` | Short tier matches smokes; medium tier extends to 4 runs × 450 iters / 45 SMBO trials for convergence comparisons. |

Heuristic sweep defaults now ride alongside the tiers: `short` → 2 runs × 200 ILS iterations / 2 runs × 1 200 Tabu iterations, `medium` → 3 runs × 350 / 3 runs × 2 000, and `long` → 5 runs × 700 (ILS) with hybrid MIP enabled / 5 runs × 3 000 (Tabu). Plan overrides tweak those numbers for smoke runs, but everything is surfaced through the tier configs so future tuners can align budgets in one place.

Guidelines:

- Seeds are derived from the base seed plus scenario index, ensuring reproducibility.
- Grid configs iterate presets before batch sizes to keep result ordering stable.
- Future tuners (e.g., neural/agentic) should target equivalent iteration/trial budgets or document deviations.
- Add a `benchmark_plan` preset to scripts and CI so the same matrix is reused locally and in automation.
- `scripts/run_tuning_benchmarks.py` accepts repeated `--tier` flags and forwards `--tier-label` to every CLI tuner so telemetry consumers can pivot by tier.
- Tier presets now cover random/grid/bayes as well as ILS/Tabu; heuristics inherit the same bundle metadata and tier contexts for pivoting in telemetry reports.
- When running wide sweeps, request at least 64 of 72 available CPU cores (`GNU parallel` or runner `--processes`) and cap per-run RSS to ≈8 GB to avoid node exhaustion.
- Use long-tier budgets when fitting convergence models (iterations to ≤1 % optimality gap) so the telemetry captures the tail behaviour needed for extrapolation.
- Convergence instrumentation: `scripts/analyze_tuner_reports.py --telemetry-log <runs.jsonl> --out-convergence-*` now scans step logs to compute iterations-to-1% gap per SA/ILS/Tabu run (requires MIP baselines in the same telemetry store). Run long-tier sweeps first so the dataset contains meaningful trajectories.

#### Latest parallel sweep
- Command: `python scripts/run_tuning_benchmarks.py --plan full-spectrum --max-workers 16 --out-dir tmp/tuning-benchmarks/full-spectrum-parallel --summary-label full-spectrum-parallel`
- Outcome: short + medium tiers completed across baseline + synthetic bundles; chunk logs merged without conflicts after `_merge_sqlite` fix; leaderboard shows Bayesian > grid/random on best objective for every scenario.
- Artefacts: see `tmp/tuning-benchmarks/full-spectrum-parallel/telemetry/` for merged JSONL/SQLite and `tuner_*` comparison/leaderboard Markdown. Next action is to rerun `scripts/analyze_tuner_reports.py` against this directory to refresh convergence summaries with the new dual-threshold metrics.

### Heuristic parameter catalogue (tuning surface)

| Layer | Parameters / flags | Typical range / notes | Tier coverage |
|-------|--------------------|------------------------|---------------|
| **Simulated Annealing (`solve-heur`, `tune-random/grid/bayes`)** | `--iters`, `--temperature0`, `--cooling-rate` | Iteration horizon (short/medium/long tiers: 150/300/600). Initial temp 50–500, cooling 0.90–0.999. | All tiers |
| | `--batch-neighbours`, `--parallel-workers` | Batch candidate sampling (1–5) with optional thread pool. | Grid presets iterate batch sizes; medium/long tiers allow worker pools. |
| | `--operator`, `--operator-weight`, `--operator-preset` | Operator enable/weights; presets `balanced`, `explore`, `mobilisation`, `agentic`. | Grid enumerates preset×batch; random/Bayesian sample weight vectors. |
| | `--multi-start`, profile extras (reheating, temperature schedules) | Multi-start count, seed progression, reheating frequency (via profiles). | Medium/long tiers may enable; Bayesian/agentic loops mutate through `tuner_meta`. |
| **Iterated Local Search (`solve-ils`, `tune-*`)** | `--iters` | Outer loop cycles: short 200, medium 350, long 700. | All tiers |
| | `--perturbation-strength`, `--stall-limit` | Diversification vs exploitation (strength 1–6, stall 8–20). | Swept in medium/long tiers and Bayesian tuner. |
| | `--hybrid-use-mip`, `--hybrid-mip-time-limit` | Trigger limited MIP restart when stalled (30–180 s). | Long tier default; optional override for experiments. |
| | Operator/preset weights, batching (`--operator*`, `--batch-neighbours`, `--parallel-workers`) | Shared registry with SA; presets keep tuners comparable. | Included through tier profiles + search spaces. |
| **Tabu Search (`solve-tabu`, `tune-*`)** | `--iters` | Iteration horizon (short 1 200 / medium 2 000 / long 3 000). | All tiers |
| | `--tabu-tenure` | Tabu list length (auto ≈ machine count; explore 20–120). | Random/Bayesian tuning + tier overrides. |
| | `--stall-limit` | Stop after non-improving steps (150–250). | Tied to tier defaults. |
| | Operator presets/weights, batching | Same registry knobs as SA/ILS for cross-tuner parity. | Search spaces reference named presets. |
| **Tuner-level budgets** | Random: `--runs`, `--iters`; Grid: `--iters`, `--batch-size`, `--preset`; Bayes: `--trials`, `--iters`, Optuna search space definition. | Tier presets (short 2×150, medium 3×300, long 5×600) + plan overrides. | Documented in bundle plan/how-to |
| **Meta / agentic extensions** | Telemetry-derived features (acceptance slope, objective gap trajectory, scenario descriptors). | Captured via `tuner_meta` and `context`; future agents mutate presets/budgets using these signals. | Planned Phase 3 deliverable |

Parameters wrapped inside profiles (cooling schedule families, operator templates, multi-start strategies) remain part of the search surface; tuning drivers surface them via preset names so Bayesian/agentic tuners can toggle discrete options without bespoke code.

### Agentic Tuning Integration
- [ ] Define prompt templates and action space for the LLM agent (config proposals, narrative rationale).
- [ ] Build agent loop driver that reads telemetry snapshots, requests proposals, validates via harness, and records outcomes.
- [ ] Add safety rails (budget limits, whitelist parameters) and log all prompts/responses for auditability.
- [ ] Document usage guidance and risks (docs/howto or dedicated guide).
- [ ] Investigate ML-driven tuner (Bayesian/SMBO or neural surrogate) leveraging the enriched telemetry schema; capture data-processing pipeline requirements (feature selection, normalisation) before implementation.
- [ ] Explore meta-telemetry driven model selection: capture tuner performance summaries so the platform can automatically choose between grid/random/Bayesian/agentic approaches per scenario class.

### Automation & Docs
- [ ] Update roadmap + docs as milestones complete.
- [x] Add Sphinx how-to covering telemetry schema, tuner commands, and agent workflow once stable.
- [x] Provide comparison tooling (`scripts/analyze_tuner_reports.py`) to diff multiple reports and surface deltas.
- [x] Publish telemetry history artefacts (minitoy + med42) to GitHub Pages for quick trend review.
- [ ] Ensure CI smoke targets exist for lightweight tuning sweeps (e.g., single random search iteration).
- [x] Schedule `fhops telemetry report` in CI/nightly to publish comparison artifacts for baseline scenarios.
- [ ] Automate a dashboard or README badge that surfaces the published delta summary so regressions are visible without opening the full report.
- [x] Tighten `_compute_history_deltas` so percentage columns remain valid and Markdown renders cleanly.
- [x] Verify README/how-to copy clearly references the Pages URL and exported delta artefacts.
- [x] Expand `DESIRED_METRICS` (e.g., downtime) once telemetry logging exposes the fields.
- [x] Emit per-scenario summary outputs (`analyze_tuner_reports --out-summary-*`) so CI can surface the leading algorithm/objective per report.

## Notes on Meta-Tuning & Literature
- Thornton, C., Hutter, F., Hoos, H. H., & Leyton-Brown, K. (2013). *Auto-WEKA: Combined Selection and Hyperparameter Optimization of Classification Algorithms*. Proceedings of KDD ’13, 847–855. https://doi.org/10.1145/2487575.2487629 — Demonstrates joint optimisation of algorithm choice and hyperparameters, effectively automating tuner selection via logged performance.
- Golovin, D., Solnik, B., Moitra, S., Kochanski, G., Karro, J., & Sculley, D. (2017). *Google Vizier: A Service for Black-Box Optimization*. Proceedings of KDD ’17, 1487–1495. https://doi.org/10.1145/3097983.3098043 — Describes a production system that deploys multiple optimisation strategies and adapts using telemetry, reinforcing the value of meta-level logging.
- Feurer, M., & Hutter, F. (2019). *Hyperparameter Optimization*. In F. Hutter, L. Kotthoff, & J. Vanschoren (Eds.), *Automated Machine Learning: Methods, Systems, Challenges* (pp. 3–33). Springer. Chapter DOI: https://doi.org/10.1007/978-3-030-05318-5_1 — Surveys meta-learning approaches that leverage historical runs for warm starts and optimiser selection, highlighting the importance of consistent scenario descriptors and schema versioning.
- Bischl, B., Binder, M., Lang, M., Pielok, T., Richter, J., Coors, S., Thomas, J., Ullmann, T., Becker, M., Boulesteix, A.-L., Deng, D., & Lindauer, M. (2023). *Hyperparameter Optimization: Foundations, Algorithms, Best Practices and Open Challenges*. *WIREs Data Mining and Knowledge Discovery*, 13(2), e1484. https://doi.org/10.1002/widm.1484 — Provides a contemporary overview of optimiser portfolios and meta-level selection, showing that combining multiple tuners improves robustness across problem classes.
- Therefore, collecting tuner-level meta-telemetry (algorithm name, budget, convergence metrics, scenario descriptors, schema version) is not overkill; it is a prerequisite for AutoML-style tuner selection, optimiser portfolios, and stacked optimisation loops.
- Local copies stashed under `docs/references/`:
  - `thornton2013-auto-weka.pdf`
  - `golovin2017-vizier.pdf`
  - `feurer2019-hpo-chapter.pdf`
  - `bischl2023-hpo-review.pdf`

## Immediate Next Steps
- [x] Add a lightweight telemetry pruning helper (`fhops telemetry prune`) that truncates `runs.jsonl` and cleans matching step logs. *(See `fhops.cli.telemetry.prune`.)*
- [x] Implement the first conventional tuner driver (`fhops tune random` execution mode) that samples solver configs and records telemetry entries.
- [x] Provide a simple JSONL → DataFrame loader in `fhops.telemetry` to make analyses/tests easier ahead of the SQLite backend.
- [x] Add scenario descriptor exporter (machines/blocks/shifts) to telemetry runs so ML tuners can generalise across instances.
- [ ] Stage benchmarking sweeps comparing grid/random/bayes on the canonical bundle and capture comparative telemetry summaries.
- [ ] Wire `scripts/run_tuning_benchmarks.py` into CI (smoke mode) so minitoy/med42 sweeps publish the summary tables automatically.
- [ ] Use the per-scenario summary CSV/Markdown to drive README badges or dashboards that flag regressions without opening full reports.

### Telemetry schema (draft)

We will persist three related record types in JSONL (phase 1) and mirror the schema in a SQLite view when we introduce structured queries.

#### TelemetryRun
| Field | Type | Notes |
| --- | --- | --- |
| `run_id` | `str` (UUID4) | Stable identifier for the tuning run. |
| `timestamp` | `datetime` (ISO8601) | Start time. |
| `solver` | `str` | e.g., `sa`, `ils`, `tabu`. |
| `scenario` | `str` | Scenario path or alias. |
| `bundle` | `str | None` | Optional benchmark bundle identifier. |
| `seed` | `int` | RNG seed. |
| `config` | `dict[str, Any]` | Flattened solver options (cooling schedule, operator weights, etc.). |
| `status` | `str` | `ok`, `timeout`, `error`. |
| `metrics` | `dict[str, float]` | Final KPIs (objective, production, utilisation, runtime). |
| `artifacts` | `list[str]` | Paths to serialized logs, solution CSVs, etc. |

#### TelemetryStep
| Field | Type | Notes |
| --- | --- | --- |
| `run_id` | `str` | Foreign key to `TelemetryRun`. |
| `step` | `int` | Iteration index (temperature step, epoch). |
| `objective` | `float` | Current best objective. |
| `temperature` | `float | None` | SA-specific cooling value. |
| `acceptance_rate` | `float | None` | Accepted moves / total. |
| `best_delta` | `float | None` | Improvement at this step. |
| `elapsed_seconds` | `float` | Wall-clock since run start. |
| `operator_stats` | `dict[str, Any]` | Usage counts/acceptance per operator. |

#### TelemetryArtifact
| Field | Type | Notes |
| --- | --- | --- |
| `run_id` | `str` | Foreign key to `TelemetryRun`. |
| `name` | `str` | e.g., `solution_csv`, `telemetry_jsonl`. |
| `path` | `str` | Relative filesystem path. |
| `mime_type` | `str` | Helps downstream ingestion. |
| `size_bytes` | `int` | Optional size metadata. |

**Storage layout (JSONL)**  
- `telemetry/runs.jsonl` — one line per `TelemetryRun` record.  
- `telemetry/steps/<run_id>.jsonl` — time-series per run (optional when step logging disabled).  
- `telemetry/artifacts.jsonl` — references for discovered outputs.

**SQLite Store (phase 2)**  
`telemetry/runs.sqlite` is created alongside the JSONL log and currently persists:
- `runs` — one row per heuristic invocation (metadata + JSON columns for config/context/extra).
- `run_metrics` — scalar metrics keyed by name (objective, acceptance rate, KPI aggregates).
- `run_kpis` — KPI totals normalised for downstream feature pipelines.
- `tuner_summaries` — per-command sweep summaries (algorithm, budget, best-by-scenario snapshots).
Foreign keys cascade deletions so `fhops telemetry prune` keeps SQLite in sync with the JSONL history.

## Telemetry storage & retention (2025-11-12)

- **Storage layout:** heuristics default to writing run records to `telemetry/runs.jsonl` and a mirrored SQLite store at `telemetry/runs.sqlite`. Step logs live beside the JSONL under `telemetry/steps/<run_id>.jsonl`. Commands accept `--telemetry-log` to override the run log path; step logs and the SQLite database are automatically co-located.
- **Rotation policy:** keep the most recent 5k runs (≈25–30 MB with current schema). For manual pruning run:

  ```bash
  tail -n 5000 telemetry/runs.jsonl > telemetry/runs.tmp && mv telemetry/runs.tmp telemetry/runs.jsonl
  find telemetry/steps -type f -mtime +14 -delete
  ```

  Future work: add `fhops telemetry prune` to automate the truncation/synchronisation process.
- **Archiving:** move older logs to `telemetry/archive/YYYYMMDD/` (both `runs.jsonl` and matching step files) before pruning if longer history is required. Compression (`xz`/`gzip`) keeps archives compact.
- **Docs & CLI:** `solve-heur`, `solve-ils`, and `solve-tabu` help text now points to the recommended `telemetry/` directory and explains step-log co-location so users adopt the shared store by default.

LLM-Driven Tuner (Agentic Auto-Tuning)
--------------------------------------

**Pros**
- *Sample efficient intuition*: agents can reason about small datasets, infer trends or cooling anomalies, and propose structured “experiments” (e.g., “try move-heavy, shorten temperature schedule”).
- *Cross-domain knowledge*: LLMs ingest guidance from papers/blogs, blending SA-specific heuristics with broader optimizer tactics.
- *Interactive adaptation*: agents inspect telemetry logs, interpret operator stats, and pivot without retraining a surrogate model.
- *Config-aware suggestions*: they can output code patches, CLI commands, or preset definitions directly, tightening the iteration loop.
- *Explainability*: they can rationalise why a configuration might work, helping humans study new heuristics.

**Cons / Risks**
- *Stochastic reasoning*: generations aren’t guaranteed to converge—prompting must be coupled with strict evaluation loops.
- *Cost/time*: running LLM-in-the-loop pipelines can be expensive compared with cheap Bayesian updates.
- *Lack of numeric rigour*: agents rely on textual reasoning rather than explicit surrogate modelling.
- *Reproducibility*: without strict logging, agentic workflows risk “prompt drift” and results that are hard to audit.

Conventional ML Approaches
--------------------------

**Bayesian Optimization, SMBO, Hyperband**
- *Pros*: mathematically grounded, proven convergence, efficient use of limited budgets.
- *Cons*: high-dimensional, categorical search spaces (operator presets + SA temperature knobs) can be brittle; surrogate models may struggle with discrete, non-smooth objectives.

**Evolutionary / Population-based Methods**
- *Pros*: robust to noisy objectives; peripheral parameters (operator weights) can evolve naturally.
- *Cons*: require many evaluations, so compute-heavy; crossover/mutation design matters.

**RL / Meta-Learning**
- *Pros*: can adaptively adjust parameters during solve (dynamic cooling schedules).
- *Cons*: complex training, data-hungry, may require expensive on-policy interactions.

Hybrid Approach
---------------

1. **Structured telemetry**: each SA/benchmark run emits JSON rows capturing scenario, seed, operator weights, acceptance metrics, final objective.
2. **Baseline tuner**: start with Bayesian optimization or Hyperband for global exploration and a reproducible baseline.
3. **LLM Agent layer**: feed accumulated telemetry (plus notes/roadmaps) to an agent that suggests new presets or weight combinations, with explanations.
4. **Iteration control**: keep an evaluation harness that validates suggestions automatically and records outcomes back into the telemetry log.

Recommendation
--------------

- Implement the persistent telemetry log (JSONL or SQLite) and capture per-operator stats.
- Launch a basic Bayesian tuner for continuous knobs to establish baseline improvements.
- Layer an LLM agent on top for periodic “insightful” suggestions, cross-checking them against the log.
- Document the schema and evaluation pipeline so future automation (including fully agentic loops) can plug in.

Documentation Maintenance
-------------------------

- After major benchmark updates, rerun ``fhops bench suite --include-ils --include-tabu`` (optionally skipping MIP) to refresh comparison data.
- Regenerate figures referenced in :doc:`docs/howto/benchmarks` via:

  .. code-block:: bash

     python scripts/render_benchmark_plots.py tmp/benchmarks_compare/summary.csv --out-dir docs/_static/benchmarks

- Audit heuristic preset examples in :doc:`docs/howto/heuristic_presets` when operators or defaults change.

## Incoming

### Gurobi license registration for optional gurobi MIP solver (when not using default HiGHS)

Add instructions to the documentation (installation notes) for pulling the lightweight gurobi license registration executable file bundle for linux from their server and using that to register an academic gurobi license from the command line (these tools are not included when gurobi installed via pip). See real example below (obviously anonymize for documentation example).

```bash
(.venv) gep@jupyterhub01:~/projects/fhops/tmp$ wget https://packages.gurobi.com/lictools/licensetools13.0.0_linux64.tar.gz
--2025-11-13 06:11:15--  https://packages.gurobi.com/lictools/licensetools13.0.0_linux64.tar.gz
Resolving packages.gurobi.com (packages.gurobi.com)... 3.175.64.15, 3.175.64.34, 3.175.64.115, ...
Connecting to packages.gurobi.com (packages.gurobi.com)|3.175.64.15|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 23089111 (22M) [binary/octet-stream]
Saving to: ‘licensetools13.0.0_linux64.tar.gz’

licensetools13.0.0_linux64.tar.gz                                   100%[=================================================================================================================================================================>]  22.02M  30.3MB/s    in 0.7s    

2025-11-13 06:11:16 (30.3 MB/s) - ‘licensetools13.0.0_linux64.tar.gz’ saved [23089111/23089111]

(.venv) gep@jupyterhub01:~/projects/fhops/tmp$ tar xvfz licensetools13.0.0_linux64.tar.gz 
grbprobe
grb_ts
grb_wlsproxy
grbgetkey
(.venv) gep@jupyterhub01:~/projects/fhops/tmp$ ./grbgetkey 021ee1de-5fb7-4490-ae90-3e8801924974
info  : grbgetkey version 13.0.0, build v13.0.0beta1
info  : Platform is linux64 (linux) - "Ubuntu 24.04.3 LTS"
info  : Contacting Gurobi license server...
info  : License file for license ID 2737116 was successfully retrieved
info  : License expires at the end of the day on 2026-11-13
info  : Saving license file...

In which directory would you like to store the Gurobi license file?
[hit Enter to store it in /home/gep]: 

info  : License 2737116 written to file /home/gep/gurobi.lic
```
