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
- [x] Shift-based scheduling architecture (data contract → solvers → KPIs) (`notes/modular_reorg_plan.md`, `notes/mip_model_plan.md`).
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
- [ ] Synthetic dataset generator & benchmarking suite (`notes/synthetic_dataset_plan.md`).
  - [ ] Design & planning
    - [ ] Finalise dataset taxonomy and parameter ranges in `notes/synthetic_dataset_plan.md`.
    - [ ] Align generator requirements with Phase 2 benchmarking harness expectations.
    - [ ] Identify storage strategy and naming for generated scenarios (`data/synthetic/`).
  - [ ] Generator implementation
    - [ ] Build core sampling utilities (terrain, system mix, downtime patterns) with tests.
    - [ ] Expose CLI entry (`fhops synth`) and configuration schema for batch generation.
    - [ ] Add validation suite ensuring generated datasets meet contract + KPI sanity bounds.
  - [ ] Benchmark integration
    - [ ] Hook synthetic scenarios into benchmark harness and CI smoke targets.
    - [ ] Provide metadata manifests describing each scenario for docs/examples.
    - [ ] Outline scaling experiments and capture results in changelog/notes.
- [ ] Reference analytics notebooks integrated into docs/examples.
  - [ ] Notebook scaffolding
    - [ ] Select representative deterministic + stochastic scenarios (baseline + synthetic).
    - [ ] Define notebook storyboards (playback walkthrough, KPI deep-dive, what-if analysis).
    - [ ] Create reusable plotting helpers (matplotlib/Altair) shared across notebooks.
  - [ ] Notebook authoring
    - [ ] Draft notebooks under `docs/examples/analytics/` with executed outputs.
    - [ ] Ensure notebooks call CLI/modules via lightweight wrappers for reproducibility.
    - [ ] Capture metadata (runtime, dependencies) and add smoke execution script.
  - [ ] Documentation & automation
    - [ ] Integrate notebooks into Sphinx (nbsphinx or nbconvert pipeline) with cross-links.
    - [ ] Add CI check to execute notebooks (or cached outputs) on critical scenarios.
    - [ ] Update README and docs landing pages to advertise analytics assets.
- [ ] Hyperparameter tuning framework (conventional + agentic) leveraging persistent telemetry (`notes/metaheuristic_hyperparam_tuning.md`).
  - [ ] Telemetry & persistence groundwork
    - [ ] Define telemetry schema (solver configuration, KPIs, runtime stats) and storage backend.
    - [ ] Implement logging hooks in solvers and playback runs, persisting to local store.
    - [ ] Document data retention/rotation strategy in tuning notes.
  - [ ] Conventional tuning toolkit
    - [ ] Implement grid/random/Bayesian search drivers leveraging telemetry store.
    - [ ] Provide CLI surfaces for launching tuning sweeps with scenario bundles.
    - [ ] Add automated comparison reports summarising best configurations per scenario class.
  - [ ] Agentic tuning integration
    - [ ] Prototype agent loop per `notes/metaheuristic_hyperparam_tuning.md` (prompt templates + action space).
    - [ ] Validate agent performance against deterministic benchmarks and log deltas.
    - [ ] Capture rollout guidelines and safety rails in docs before broader rollout.

## Phase 4 — Release & Community Readiness
- [ ] Complete Sphinx documentation set (API, CLI, how-tos, examples) published to Read the Docs.
- [ ] Finalise contribution guide, code of conduct alignment, and PR templates.
- [ ] Versioned release notes and public roadmap updates.
- [ ] Outreach plan (blog, seminars, partner briefings).

## Detailed Next Steps
1. **Shift-Based Scheduling Initiative (`notes/modular_reorg_plan.md`, `notes/mip_model_plan.md`)**
   - Design shift-aware data contract extensions, update solver indices, and migrate KPIs/benchmarks to operate per shift.
2. **Metaheuristic Roadmap (`notes/metaheuristic_roadmap.md`)**
   - Prioritise SA refinements, operator registry work, and benchmarking comparisons with the new harness (including shift-aware neighbourhoods).
3. **Harvest System Sequencing Plan (`notes/system_sequencing_plan.md`)**
   - Close parity gaps between MIP/heuristic sequencing and add stress tests for machine-to-system mapping.
4. **CLI & Documentation Plan (`notes/cli_docs_plan.md`)**
   - Introduce solver configuration profiles/presets and document shift-based workflows in the CLI reference.
5. **Simulation & Evaluation Plan (`notes/simulation_eval_plan.md`)**
   - Prepare deterministic/stochastic playback for shift timelines and extended KPI reporting ahead of Phase 3.

## Backlog & Ideas
- [ ] Integration with Nemora sampling outputs for downstream operations analytics.
- [ ] Scenario authoring UI and schema validators for web clients.
- [ ] Cloud execution harness for large-scale heuristics.
- [ ] DSS integration hooks (ArcGIS, QGIS) for geo-enabled workflows.
- [ ] Jaffray MASc thesis alignment checkpoints (`notes/thesis_alignment.md` TBD).
