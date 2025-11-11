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
- [ ] Implement logging hooks in SA/ILS/Tabu solvers and playback validators writing to JSONL (phase 1) and SQLite (optional phase 2).
  - [x] Simulated Annealing JSONL prototype: run + step telemetry recorded via `RunTelemetryLogger`.
- [x] Provide helper module (`fhops.telemetry.run_logger`) with append/query utilities and retention controls.
- [ ] Document retention/rotation strategy and storage location in this note + CLI help.

### Conventional Tuning Toolkit
- [ ] Implement grid and random search drivers operating on the telemetry store (CLI-friendly).
- [ ] Integrate a Bayesian/SMBO tuner (e.g., Optuna or scikit-optimize) with pluggable search spaces.
- [ ] Expose CLI commands (`fhops tune random`, `fhops tune bayes`) that schedule sweeps over scenario bundles.
  - [x] Placeholder `fhops tune-random` surfaces latest telemetry records while full tuner is built.
- [ ] Generate automated comparison reports (CSV/Markdown) summarising best configs per scenario tier; stash fixtures/tests.

### Agentic Tuning Integration
- [ ] Define prompt templates and action space for the LLM agent (config proposals, narrative rationale).
- [ ] Build agent loop driver that reads telemetry snapshots, requests proposals, validates via harness, and records outcomes.
- [ ] Add safety rails (budget limits, whitelist parameters) and log all prompts/responses for auditability.
- [ ] Document usage guidance and risks (docs/howto or dedicated guide).

### Automation & Docs
- [ ] Update roadmap + docs as milestones complete.
- [ ] Add Sphinx how-to covering telemetry schema, tuner commands, and agent workflow once stable.
- [ ] Ensure CI smoke targets exist for lightweight tuning sweeps (e.g., single random search iteration).

## Immediate Next Steps
- [x] Sketch telemetry schema (`TelemetryRun`, `TelemetryStep`, `TelemetryArtifact`) and align with existing solver stats; capture preliminary schema diagram in this note.
- [x] Prototype JSONL logger in Simulated Annealing driver (write via context manager) and add unit smoke test capturing a sample record.
- [x] Draft CLI stub (`fhops tune random`) that accepts scenario bundle paths and prints parsed telemetry entries (placeholder implementation).

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
