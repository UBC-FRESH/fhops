# Simulation & Evaluation Plan

Date: 2025-??-??
Status: Draft — roadmap Phase 3 owner document.

## Objectives
- Extend deterministic playback engine with stochastic modules (downtime, weather, landing congestion).
- Support shift-level playback with aggregation to day/week calendars and blackout reporting.
- Expand KPI reporting (cost, utilisation, lateness, mobilisation spend) with configurable outputs (CSV, parquet, dashboards).
- Integrate with Nemora outputs for joint scenario analysis.

## Work Items
- [ ] Audit existing evaluation pipeline (`fhops/eval` → future `evaluation/playback`).
- [ ] Design stochastic sampling API (RNG seeding, scenario ensembles).
- [ ] Implement shift-aware KPI calculators with unit tests and docs.
- [ ] Capture mobilisation-related metrics and reporting hooks.
- [ ] Prototype Nemora integration (import stand tables as stress tests).

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
