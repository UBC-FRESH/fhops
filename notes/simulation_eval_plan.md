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
