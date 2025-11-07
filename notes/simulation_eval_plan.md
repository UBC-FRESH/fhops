# Simulation & Evaluation Plan

Date: 2025-??-??
Status: Draft — roadmap Phase 3 owner document.

## Objectives
- Extend deterministic playback engine with stochastic modules (downtime, weather, landing congestion).
- Expand KPI reporting (cost, utilisation, lateness) with configurable outputs (CSV, parquet, dashboards).
- Integrate with Nemora outputs for joint scenario analysis.

## Work Items
- [ ] Audit existing evaluation pipeline (`fhops/eval`).
- [ ] Design stochastic sampling API (RNG seeding, scenario ensembles).
- [ ] Implement KPI calculators with unit tests and docs.
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
