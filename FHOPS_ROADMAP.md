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
- [ ] Metaheuristic roadmap execution (Simulated Annealing refinements, Tabu/ILS activation).
- [x] Mobilisation penalty calibration & distance QA across benchmark scenarios (`notes/mobilisation_plan.md`).
- [ ] Harvest system sequencing parity and machine-to-system mapping (`notes/system_sequencing_plan.md`).
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
1. **Metaheuristic Roadmap (`notes/metaheuristic_roadmap.md`)**
   - Prioritise SA refinements, operator registry work, and benchmarking comparisons with the new harness.
2. **Harvest System Sequencing Plan (`notes/system_sequencing_plan.md`)**
   - Close parity gaps between MIP/heuristic sequencing and add stress tests for machine-to-system mapping.
3. **CLI & Documentation Plan (`notes/cli_docs_plan.md`)**
   - Introduce solver configuration profiles/presets exposed via CLI and Sphinx reference.
4. **MIP Model Plan (`notes/mip_model_plan.md`)**
   - Focus on performance instrumentation (build/solve timings), advanced objective variants, and HiGHS tuning.
5. **Simulation & Evaluation Plan (`notes/simulation_eval_plan.md`)**
   - Begin planning stochastic playback and extended KPI reporting for Phase 3 transition.

## Backlog & Ideas
- [ ] Integration with Nemora sampling outputs for downstream operations analytics.
- [ ] Scenario authoring UI and schema validators for web clients.
- [ ] Cloud execution harness for large-scale heuristics.
- [ ] DSS integration hooks (ArcGIS, QGIS) for geo-enabled workflows.
- [ ] Jaffray MASc thesis alignment checkpoints (`notes/thesis_alignment.md` TBD).
