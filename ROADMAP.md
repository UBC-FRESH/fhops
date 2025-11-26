# FHOPS Roadmap

This roadmap orchestrates FHOPS’ evolution into a production-ready planning platform. It
mirrors the multi-level planning system pioneered in Nemora: top-level phases here, with
module-specific execution plans living in `notes/`. Update the checklist status and the
"Detailed Next Steps" section as deliverables land. When in doubt, consult the linked notes
before proposing new work.

## Phase 0 — Repository Foundations ✅ (complete)
- Initial project scaffold (`pyproject.toml`, CLI entry point, examples).
- Baseline tests covering core data contract and solver smoke cases.
- Basic README explaining architecture and usage.

## Phase 1 — Core Platform Hardening ✅ (complete)
- [x] Harden data contract validations and scenario loaders (see `notes/data_contract_enhancements.md` and `docs/howto/data_contract.rst`).
- [x] Expand Pyomo model coverage for production constraints and objective variants (see `notes/mip_model_plan.md`).
- [x] Stand up modular scaffolding (`notes/modular_reorg_plan.md`) and shift-level scheduling groundwork (`scheduling/timeline` + timeline-integrated solvers).
- [x] Establish deterministic regression fixtures for MIP and heuristic solvers.
- [x] Document baseline workflows in Sphinx (overview + quickstart).
- [x] Stand up CI enforcing the agent workflow command suite on every push and PR (see `notes/ci_cd_expansion.md`).
- [x] Define geospatial ingestion strategy for block geometries (GeoJSON baseline, distance matrix fallback) to support mobilisation costs (`notes/mobilisation_plan.md`, `notes/data_contract_enhancements.md`, `docs/howto/data_contract.rst`).

## Phase 2 — Solver & Heuristic Expansion
- [x] Scenario scaling benchmarks & tuning harness (phase kickoff task).
- [ ] Shift-based scheduling architecture (data contract → solvers → KPIs) (`notes/modular_reorg_plan.md`, `notes/mip_model_plan.md`, `notes/simulation_eval_plan.md`).
- [x] Metaheuristic roadmap execution (Simulated Annealing refinements, Tabu/ILS activation).
- [x] Mobilisation penalty calibration & distance QA across benchmark scenarios (`notes/mobilisation_plan.md`).
- [x] Harvest system sequencing parity and machine-to-system mapping (`notes/system_sequencing_plan.md`).
- [x] CLI ergonomics for solver configuration profiles.

## Phase 3 — Evaluation & Analytics
- [x] Robust schedule playback with stochastic extensions (downtime/weather sampling) and shift/day reporting.
  - [x] Playback engine audit
    - [x] Inventory deterministic playback path (`fhops/eval`, `scheduling/timeline`) and capture gaps in `notes/simulation_eval_plan.md`.
    - [x] Spec shift/day reporting interfaces and required data contract updates.
    - [x] Produce migration checklist for refactoring playback modules and regression fixtures.
  - [x] Stochastic sampling extensions
    - [x] Design RNG seeding + scenario ensemble API and land it as a draft in `notes/simulation_eval_plan.md`.
    - [x] Implement downtime/weather sampling operators with unit and property-based tests.
    - [x] Integrate sampling toggles into CLI/automation commands (document defaults in `docs/howto/evaluation.rst`).
  - [x] Shift/day reporting deliverables
    - [x] Define aggregation schemas for shift/day calendars and extend KPI dataclasses.
    - [x] Add exporters (CSV/Parquet + Markdown summary) wired into playback CLI.
    - [x] Validate outputs across benchmark scenarios and stash fixtures for CI smoke runs.
- [x] KPI expansion (cost, makespan, utilisation, mobilisation spend) with reporting templates.
  - [x] Metric specification & alignment
    - [x] Reconcile definitions across `notes/mip_model_plan.md`, `notes/mobilisation_plan.md`, and simulation notes.
    - [x] Document final KPI formulas and assumptions in `docs/howto/evaluation.rst`.
    - [x] Map required raw signals from playback outputs and ensure data contract coverage.
  - [x] Implementation & validation
    - [x] Extend KPI calculators to emit cost, makespan, utilisation, mobilisation spend variants.
    - [x] Add regression fixtures and property-based checks confirming KPI ranges per scenario tier.
    - [x] Wire KPIs into CLI reporting with configurable profiles and smoke tests.
  - [x] Reporting templates
    - [x] Draft tabular templates (CSV/Markdown) plus optional visuals for docs/notebooks.
    - [x] Provide Sphinx snippets and CLI help examples showcasing new KPI bundles.
    - [x] Capture follow-up backlog items for advanced dashboards (e.g., Plotly) if deferred (defer to backlog).
- [x] Synthetic dataset generator & benchmarking suite (`notes/synthetic_dataset_plan.md`).
  - [x] Design & planning
    - [x] Finalise dataset taxonomy and parameter ranges in `notes/synthetic_dataset_plan.md`.
    - [x] Align generator requirements with Phase 2 benchmarking harness expectations.
    - [x] Identify storage strategy and naming for generated scenarios (`data/synthetic/`).
  - [x] Generator implementation
    - [x] Build core sampling utilities (terrain, system mix, downtime patterns) with tests.
    - [x] Expose CLI entry (`fhops synth`) and configuration schema for batch generation.
    - [x] Add validation suite ensuring generated datasets meet contract + KPI sanity bounds.
  - [x] Benchmark integration
    - [x] Hook synthetic scenarios into benchmark harness and CI smoke targets.
    - [x] Provide metadata manifests describing each scenario for docs/examples.
    - [x] Outline scaling experiments and capture results in changelog/notes.
- [x] Reference analytics notebooks integrated into docs/examples.
  - [x] Notebook scaffolding
    - [x] Select representative deterministic + stochastic scenarios (baseline + synthetic).
    - [x] Define notebook storyboards (playback walkthrough, KPI deep-dive, what-if analysis).
    - [x] Create reusable plotting helpers (matplotlib/Altair) shared across notebooks.
  - [x] Notebook authoring
    - [x] Draft notebooks under `docs/examples/analytics/` with executed outputs.
    - [x] Ensure notebooks call CLI/modules via lightweight wrappers for reproducibility.
    - [x] Capture metadata (runtime, dependencies) and add smoke execution script.
  - [x] Documentation & automation
    - [x] Integrate notebooks into Sphinx (nbsphinx or nbconvert pipeline) with cross-links.
    - [x] Add CI check to execute notebooks (or cached outputs) on critical scenarios.
    - [x] Update README and docs landing pages to advertise analytics assets.
- [ ] Hyperparameter tuning framework (conventional + agentic) leveraging persistent telemetry (`notes/metaheuristic_hyperparam_tuning.md`).
  - [x] Telemetry & persistence groundwork
    - [x] Define telemetry schema (solver configuration, KPIs, runtime stats) and storage backend (drafted in `notes/metaheuristic_hyperparam_tuning.md`).
    - [x] Implement logging hooks in solvers and playback runs, persisting to local store.
      - [x] Simulated Annealing JSONL run logger emitting run/step telemetry (`RunTelemetryLogger`, `solve_sa`).
      - [x] ILS + Tabu telemetry integration (run/step logging, CLI wiring).
      - [x] Playback CLI telemetry (run metadata + step logging for day summaries).
      - [x] Enrich telemetry with scenario descriptors and schema versioning for ML tuners.
    - [x] Document data retention/rotation strategy in tuning notes.
  - [ ] Conventional tuning toolkit
    - [x] Implement grid/random/Bayesian search drivers leveraging telemetry store.
    - [x] Provide CLI surfaces for launching tuning sweeps with scenario bundles.
      - [x] Random tuner CLI (`fhops tune-random`) executing SA sweeps and recording telemetry.
      - [x] Bayesian/SMBO tuner CLI (`fhops tune-bayes`) built on Optuna.
    - [x] Automate CI sweeps (minitoy + med42) that publish `fhops telemetry report` artifacts and history summaries for baseline scenarios (CSV/MD/HTML + published chart).
    - [ ] After merging Phase 3 PR, verify GitHub Pages deployment on `main` (ensure `telemetry/history_summary.html` loads).
      - [x] Grid tuner CLI (`fhops tune-grid`) evaluating preset/batch-size combinations.
    - [x] Add automated comparison reports summarising best configurations per scenario class.
    - [ ] Benchmark tuner strategies (grid vs. random vs. Bayesian/SMBO vs. neural/agentic) and log meta-telemetry for automated model selection.
    - [x] Introduce dual convergence thresholds (soft ≤5%, hard ≤1%) in telemetry analytics so automated stopping criteria have rich signals.
    - [x] Parallelise the tuning harness (≈16 worker processes × 4 threads) with per-worker telemetry merge so sweeps scale linearly with hardware.
    - [x] Add optional Gurobi backend (`fhops[gurobi]`, `--driver gurobi`) for MIP solves that outgrow HiGHS.
    - [x] Run long-horizon convergence sweeps (SA/ILS/Tabu, ≥10 000 iterations) on baseline + synthetic bundles to measure iteration/runtime scaling and tune stopping heuristics.
      - `tmp/convergence-long/long_run_summary.csv` captures wall-clock rates and gap progress; only SA/ILS on `synthetic-medium` reached ≤5 % gap within 10 000 iterations, highlighting the need for deeper budgets or enhanced operators elsewhere.
      - Next: rerun SA/ILS/Tabu with ≥MIP wall-clock budgets (≥10 min) and log Z* vs. iteration/time curves for regression against scenario size/difficulty.
    - [ ] Reporting polish
      - [x] Tighten `_compute_history_deltas` so percentage columns remain valid and Markdown renders cleanly.
      - [x] Confirm README + docs/how-to explicitly reference the GitHub Pages URL and the exported delta artefacts.
      - [x] Expand `DESIRED_METRICS` (e.g., downtime) once telemetry logging exposes the required fields.
  - [ ] Agentic tuning integration *(deferred — see Backlog & Ideas; focus remains on conventional toolkit completion).*

## Phase 4 — Release & Community Readiness
- [x] Complete Sphinx documentation set (API, CLI, how-tos, examples) published to Read the Docs (`notes/sphinx-documentation.md`, `docs/howto/release_playbook.rst`, `docs/howto/telemetry_ops.rst`, `docs/howto/thesis_eval.rst`, API narrative guides).
  - 2025-11-24: Closed the Sphinx/docstring audit (feature/api-docstring-enhancements) — all CLI, evaluation, heuristics, and productivity modules now ship NumPy-style docstrings and Sphinx builds are warning-free.
- [x] Finalise contribution guide, code of conduct alignment, and PR templates (see `docs/howto/release_playbook.rst`, `CONTRIBUTING.md`, `AGENTS.md`).
- [x] Versioned release notes and public roadmap updates (`docs/releases/v1.0.0-alpha1.md`, `docs/releases/v0.1.0.md`, `ROADMAP.md` current).
- [ ] Outreach plan (blog, seminars, partner briefings).

## Detailed Next Steps
1. **Release Candidate Prep (`notes/release_candidate_prep.md`, `AGENTS.md`, `notes/cli_docs_plan.md`)**
   - Lock feature set, refresh install/docs, and draft release notes + Hatch-based packaging checklist ahead of the public milestone.
2. **Metaheuristic Roadmap (`notes/metaheuristic_roadmap.md`)**
   - Prioritise SA refinements, operator registry work, and benchmarking comparisons with the new harness (including shift-aware neighbourhoods).
3. **Shift-Based Scheduling Refactor (`notes/modular_reorg_plan.md`, `notes/mip_model_plan.md`, `notes/simulation_eval_plan.md`)**
   - Add shift-indexed data contract fields/validators, migrate loaders + fixtures, update MIP/heuristic decision variables to `(day, shift)` granularity, and extend playback/KPI exports plus CLI/docs to surface shift-level results.
4. **Harvest System Sequencing Plan (`notes/system_sequencing_plan.md`)**
   - Close parity gaps between MIP/heuristic sequencing and add stress tests for machine-to-system mapping.
5. **CLI & Documentation Plan (`notes/cli_docs_plan.md`)**
   - Introduce solver configuration profiles/presets and document shift-based workflows in the CLI reference.
6. **Simulation & Evaluation Plan (`notes/simulation_eval_plan.md`)**
   - Prepare deterministic/stochastic playback for shift timelines and extended KPI reporting ahead of Phase 3.
7. **Telemetry Dashboards & Reporting Polish (`docs/howto/telemetry_tuning.rst`, `docs/reference/dashboards.rst`)**
   - Add interpretation/playbook sections for each published dashboard, embed consolidated landing views (iframes or raw HTML) into Sphinx, and backfill testing/automation notes so CI coverage extends to the full notebook suite.
   - Automate a weekly “full” analytics notebook run (no `--light`) via a scheduled GitHub Actions workflow that uploads refreshed artefacts to the telemetry bundle and alerts if any notebook fails.
   - Capture operational expectations (rotation owners, notification channel, artifact retention) in `notes/metaheuristic_hyperparam_tuning.md` once the workflow lands.
8. **Productivity Modeling & Helper Rollout (`notes/dataset_inspection_plan.md`, `docs/reference/harvest_systems.rst`)**
   - [x] Ship CTL forwarder helper module (`fhops.productivity.forwarder_bc`) covering Ghaffariyan small/large, Kellogg mixed/saw/pulp, and FPInnovations ADV6N10 sorting models, with CLI/test coverage and planning notes.
   - [x] Ship CTL harvester helpers (ADV6N10 regression + CLI, ADV5N30 removal/brushing modifiers, TN292 tree-size/density regression) and document applicability in the CLI/docs.
   - [x] Record TN285 / ADV5N9 / ADV2N21 scenario guidance (ghost trails, removal levels, trail reuse) in the planning docs so scenario authors know when productivity stays flat vs. when to adjust costs.
   - [x] Integrate the new helpers into dataset inspection CLI defaults and synthetic generator presets; refresh fixtures/tests that assume legacy productivity values (landing processor/loader coverage now fully wired, docs/tests refreshed).
   - [x] Keep `ROADMAP.md` and `notes/dataset_inspection_plan.md` in sync as additional FPInnovations regressions are ported.
   - **Next focus:** with the TN258 monthly support split, Hi-Skid costing, and ADV4N7/ADV15N3 penalties now wired directly into the cost helper, pivot to the November 2025 FPInnovations drop scan (TN122+/ADV salvage set) so the outstanding “new PDF” backlog can close without waiting for fresh references.

## Backlog & Ideas
- [ ] Agentic tuner R&D (prompt loop, guardrails, benchmarking) — revisit once the conventional tuning suite and reporting pipeline are stable.
- [ ] Integration with Nemora sampling outputs for downstream operations analytics.
- [ ] Scenario authoring UI and schema validators for web clients.
- [ ] Cloud execution harness for large-scale heuristics.
- [ ] DSS integration hooks (ArcGIS, QGIS) for geo-enabled workflows.
- [ ] Jaffray MASc thesis alignment checkpoints (`notes/thesis_alignment.md` TBD).
- [ ] VSCode keeps firing web apps on various random-sounding ports while running `injest_mip_baselines.py` and other benchmarking scripts? What is up with that? It is annoyingly resulting in VSCode interface popping up "Your application is running on port XXXX" messages (becaue of the built-in port-forwarding proxy).
- [ ] Schedule “full” analytics notebook runs (no light flag) on a less frequent cadence (nightly or weekly: leaning towards weekly) to guard against stochastic regression while keeping CI duration manageable.
  - [ ] Extend CI with a `cron` job that invokes `scripts/run_analytics_notebooks.py --timeout 900` (no `--light`) and publishes the resulting reports to the telemetry Pages bundle, keeping a 4-week artifact history for comparison.
- [ ] `pre-commit` autoupdate (especially `pre-commit-hooks`) plus workflow wiring so stage deprecation warnings are resolved before upstream removal.
- [ ] Dataset inspection + data-quality polish (see `notes/dataset_inspection_plan.md`)
  - [ ] Enforce/document 24 h/day machine availability in docs + sample datasets, and flag deviations via the inspector CLI.
