# Data Contract Enhancements Plan

Date: 2025-??-??
Status: Draft — update as tasks progress.

## Objectives
- Tighten Pydantic models for scenarios, including cross-field validation and informative errors.
- Expand IO helpers for CSV/YAML consistency, defaults, and schema evolution.
- Provide fixtures and docs so contributors can craft valid scenarios quickly.

## Planned Work
- [ ] Audit existing `fhops.core` models for missing constraints (e.g., non-negative work, horizon bounds).
- [ ] Add schema-level validators ensuring linked IDs exist across CSV inputs.
- [ ] Introduce typed helpers for optional extras (geo metadata, crew assignments).
- [ ] Document data contract extensions in Sphinx (`docs/howto/data_contract.rst`).

## Tests & Tooling
- [ ] Property-based or parametrised tests covering edge-case scenarios.
- [ ] Regression fixtures under `tests/data/` representing minimal, typical, and invalid cases.

## Documentation
- [ ] Draft how-to guide(s) for authoring scenarios and validating inputs.
- [ ] Update README quickstart once new constraints land.

## Open Questions
- Should invalid references be fatal or downgraded to warnings with heuristic fixes?
- How do we version the data contract as fields evolve (semver vs schema tags)?
