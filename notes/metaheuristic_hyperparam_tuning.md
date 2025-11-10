Metaheuristic Hyperparameter Tuning Plan
========================================

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
