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
- [x] Document retention/rotation strategy and storage location in this note + CLI help.
- [x] Introduce scenario descriptor capture (block/machine counts, horizon, landing stats) so tuners can learn across instances.
- [x] Add schema versioning to run/step records and document the schema contract to de-risk future consumers.
- [ ] Persist KPI outcomes / objective components in a normalised telemetry table (SQLite phase) for ML feature pipelines.

### Conventional Tuning Toolkit
- [ ] Implement grid and random search drivers operating on the telemetry store (CLI-friendly).
  - [x] Grid tuner execution mode (`fhops tune-grid`) evaluating preset/batch-size cartesian products with telemetry logging.
  - [x] Random tuner execution mode (`fhops tune-random`) running SA sweeps and recording telemetry.
- [ ] Integrate a Bayesian/SMBO tuner (e.g., Optuna or scikit-optimize) with pluggable search spaces.
- [ ] Expose CLI commands (`fhops tune random`, `fhops tune bayes`) that schedule sweeps over scenario bundles.
- [ ] Generate automated comparison reports (CSV/Markdown) summarising best configs per scenario tier; stash fixtures/tests.
- [ ] Benchmark grid vs. random vs. Bayesian/SMBO (and future neural/meta-learned) tuners across canonical scenarios; log comparative telemetry (win rate, best obj delta, runtime).
- [ ] Emit tuner-level meta-telemetry (algorithm name, configuration, budget, convergence stats) so higher-level orchestration can evaluate tuner performance.

### Agentic Tuning Integration
- [ ] Define prompt templates and action space for the LLM agent (config proposals, narrative rationale).
- [ ] Build agent loop driver that reads telemetry snapshots, requests proposals, validates via harness, and records outcomes.
- [ ] Add safety rails (budget limits, whitelist parameters) and log all prompts/responses for auditability.
- [ ] Document usage guidance and risks (docs/howto or dedicated guide).
- [ ] Investigate ML-driven tuner (Bayesian/SMBO or neural surrogate) leveraging the enriched telemetry schema; capture data-processing pipeline requirements (feature selection, normalisation) before implementation.
- [ ] Explore meta-telemetry driven model selection: capture tuner performance summaries so the platform can automatically choose between grid/random/Bayesian/agentic approaches per scenario class.

### Automation & Docs
- [ ] Update roadmap + docs as milestones complete.
- [ ] Add Sphinx how-to covering telemetry schema, tuner commands, and agent workflow once stable.
- [ ] Ensure CI smoke targets exist for lightweight tuning sweeps (e.g., single random search iteration).

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

**SQLite (phase 2)**  
Mirrors the same schema with `runs`, `steps`, `artifacts` tables plus indexes on `(scenario, solver)` and `(run_id)` to accelerate queries.

## Telemetry storage & retention (2025-11-12)

- **Storage layout:** heuristics default to writing run records to `telemetry/runs.jsonl`. Step logs live beside it under `telemetry/steps/<run_id>.jsonl`. Commands accept `--telemetry-log` to override the run log path; step logs are automatically co-located.
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
