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

## Phase 1 — Core Platform Hardening 🚧 (in progress)
- [ ] Harden data contract validations and scenario loaders (see `notes/data_contract_enhancements.md`).
- [ ] Expand Pyomo model coverage for production constraints and objective variants (see `notes/mip_model_plan.md`).
- [ ] Stand up modular scaffolding (`notes/modular_reorg_plan.md`) and shift-level scheduling groundwork (`scheduling/timeline`).
- [ ] Establish deterministic regression fixtures for MIP and heuristic solvers.
- [ ] Document baseline workflows in Sphinx (overview + quickstart).
- [ ] Stand up CI enforcing the agent workflow command suite on every push and PR.

## Phase 2 — Solver & Heuristic Expansion
- [ ] Metaheuristic roadmap execution (Simulated Annealing refinements, Tabu/ILS activation).
- [ ] Mobilisation/setup cost integration in MIP & heuristics (`notes/mobilisation_plan.md`).
- [ ] Harvest system sequencing constraints and machine-to-system mapping (`notes/system_sequencing_plan.md`).
- [ ] Scenario scaling benchmarks and tuning harness.
- [ ] CLI ergonomics for solver configuration profiles.

## Phase 3 — Evaluation & Analytics
- [ ] Robust schedule playback with stochastic extensions (downtime/weather sampling) and shift/day reporting.
- [ ] KPI expansion (cost, makespan, utilisation, mobilisation spend) with reporting templates.
- [ ] Synthetic dataset generator & benchmarking suite (`notes/synthetic_dataset_plan.md`).
- [ ] Reference analytics notebooks integrated into docs/examples.

## Phase 4 — Release & Community Readiness
- [ ] Complete Sphinx documentation set (API, CLI, how-tos, examples) published to Read the Docs.
- [ ] Finalise contribution guide, code of conduct alignment, and PR templates.
- [ ] Versioned release notes and public roadmap updates.
- [ ] Outreach plan (blog, seminars, partner briefings).

## Detailed Next Steps
1. **Data Contract Enhancements (`notes/data_contract_enhancements.md`)**
   - Immediate focus: tighten Pydantic models, add schema-level validation tests, document custom field semantics.
2. **MIP Model Plan (`notes/mip_model_plan.md`)**
   - Track constraint/objective backlog, regression scenarios, and solver performance tuning tasks.
3. **Metaheuristic Roadmap (`notes/metaheuristic_roadmap.md`)**
   - Capture operator library expansion, calibration experiments, and benchmarking coverage.
4. **Simulation & Evaluation Plan (`notes/simulation_eval_plan.md`)**
   - Coordinate deterministic/stochastic playback features, KPI extensions, and test fixtures.
5. **CLI & Documentation Plan (`notes/cli_docs_plan.md`)**
   - Align CLI UX improvements, doc content development, Sphinx/RTD publishing workflow.
6. **CI/CD Expansion Plan (`notes/ci_cd_expansion.md`)**
   - Owns automation backlog: GitHub Actions, coverage, dependency caching, release pipelines.

## Backlog & Ideas
- [ ] Integration with Nemora sampling outputs for downstream operations analytics.
- [ ] Scenario authoring UI and schema validators for web clients.
- [ ] Cloud execution harness for large-scale heuristics.
- [ ] DSS integration hooks (ArcGIS, QGIS) for geo-enabled workflows.
- [ ] Jaffray MASc thesis alignment checkpoints (`notes/thesis_alignment.md` TBD).
