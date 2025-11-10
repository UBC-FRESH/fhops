# Simulation & Evaluation Plan

Date: 2025-??-??
Status: Draft — roadmap Phase 3 owner document.

## Objectives
- Extend deterministic playback engine with stochastic modules (downtime, weather, landing congestion).
- Support shift-level playback with aggregation to day/week calendars and blackout reporting (align with Phase 2 shift-based scheduling initiative).
- Expand KPI reporting (cost, utilisation, lateness, mobilisation spend) with configurable outputs (CSV, parquet, dashboards).
- Integrate with Nemora outputs for joint scenario analysis.

## Work Items
- [ ] Audit existing evaluation pipeline (`fhops/eval` → future `evaluation/playback`).
- [ ] Design stochastic sampling API (RNG seeding, scenario ensembles).
- [ ] Implement shift-aware KPI calculators with unit tests and docs.
- [ ] Capture mobilisation-related metrics and reporting hooks.
- [ ] Prototype Nemora integration (import stand tables as stress tests).

### Deterministic Playback Inventory — 2025-02-??
- **Current assets**
  - Legacy `fhops.eval.kpis` simply re-exports `fhops.evaluation.metrics.kpis.compute_kpis`; the latter is still the working KPI entry point (expects a day-level assignments `DataFrame` with `machine_id`, `block_id`, `day` columns).
  - `Scenario` contracts expose `timeline`, `calendar`, and optional `shift_calendar` fields plus `TimelineConfig`/`ShiftDefinition`/`BlackoutWindow` models in `fhops.scheduling.timeline` for describing shift structures.
  - Heuristic solvers (`fhops.optimization.heuristics.sa`) emit `Schedule.plan` dictionaries keyed by `(day, shift_id)` and already consult blackout windows + shift availability, so raw schedule data is available for playback.
- **Gaps to close**
  - `fhops.evaluation.playback` is an empty namespace; there is no deterministic playback engine to transform solver outputs into time-indexed records or to stitch together shift/day aggregates.
  - No bridge converts `Schedule.plan` (or MIP outputs) into the tabular format consumed by `compute_kpis`; downstream consumers hand-roll conversions in notebooks/tests.
  - CLI layer lacks a playback/evaluation command; documentation only references KPI helpers via solver examples.
  - Reporting primitives stop at day-level metrics—no shift/day rollups, blackout reporting, or mobilisation timelines exist.
  - Regression coverage is limited to KPI calculators; there are no fixtures validating end-to-end playback or ensuring calendars/timelines are honoured.
  - Deprecation warning for `fhops.eval.kpis` remains—needs removal once new playback module lands to avoid dual entry points.

## Testing Strategy
- [ ] Regression fixtures representing deterministic and stochastic runs.
- [ ] Property-based checks to ensure KPIs remain within expected bounds.

## Documentation
- [ ] Author Sphinx how-to for evaluation workflows.
- [ ] Provide notebook-style examples demonstrating robustness analysis.

## Open Questions
- How to manage runtime for Monte Carlo simulations in CI?
- Should KPI outputs support plugin architecture for custom metrics?
# Scenario & Solver Benchmarking Plan

## Phase 2 Kickoff (2025-11-XX)
- **Objective:** Establish a repeatable harness that measures MIP + SA performance across the
  bundled scenarios (`examples/minitoy`, `examples/med42`, `examples/large84`) and captures
  core metrics (build/solve time, objective components, KPI outputs).
- **Deliverables:**
  1. CLI/automation entry-point (e.g., `fhops bench`) running the benchmark suite.
  2. Structured outputs (CSV/JSON) with solver timings and KPI snapshots stored under
     `tmp/benchmarks/` (configurable) plus regression-friendly fixtures for lightweight CI.
  3. Documentation covering how to run the harness and interpret results (`docs/howto/benchmarks.rst`
     or quickstart addendum).
  4. Notes summarising benchmark expectations and follow-up tasks (calibration, regression guards).
- **References:** `notes/metaheuristic_roadmap.md`, `notes/mip_model_plan.md`,
  `docs/howto/quickstart.rst`, `examples/*`.

## Outstanding Tasks
- [x] Requirements sweep (collect expectations from roadmap notes, confirm metrics/KPI coverage).
- [x] Scaffold harness script/module with CLI integration.
- [x] Implement JSON/CSV result emission + optional baseline fixture.
- [x] Add documentation section describing usage.
- [x] Add pytest smoke (marked `benchmark`) for minitoy harness run.
- [x] Update roadmap + changelog upon completion.
