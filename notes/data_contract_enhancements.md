# Data Contract Enhancements Plan

Date: 2025-??-??
Status: Draft — update as tasks progress.

## Objectives
- Tighten Pydantic models for scenarios, including cross-field validation and informative errors.
- Add support for shift-level scheduling (per-shift calendars, blackout rules) while retaining day/week reporting hooks.
- Represent harvest systems, machine capabilities, and worker training matrices in the contract.
- Expand IO helpers for CSV/YAML consistency, defaults, and schema evolution.
- Provide fixtures and docs so contributors can craft valid scenarios quickly.
- Introduce optional geospatial ingest (GeoJSON block footprints) with automatic distance-matrix generation for mobilisation costs.

## Planned Work
- [ ] Audit existing `fhops.core` models for missing constraints (e.g., non-negative work, horizon bounds).
- [x] Introduce shift calendar models (per-shift durations, blackout dates, weekly rollups). *(TimelineConfig added; scheduling integration pending usage.)*
- [x] Introduce mobilisation schema (machine parameters, block distances). *(MobilisationConfig added; needs wiring into optimisation.)*
- [ ] Add schema-level validators ensuring linked IDs exist across CSV inputs (blocks↔systems↔machines↔workers).
- [ ] Introduce typed helpers for optional extras (geo metadata, crew assignments).
- [ ] Document data contract extensions in Sphinx (`docs/howto/data_contract.rst`).
- [ ] Specify GeoJSON ingestion schema (accepted CRS, required block properties) and distance computation workflow.

## Tests & Tooling
- [ ] Property-based or parametrised tests covering edge-case scenarios.
- [ ] Regression fixtures under `tests/data/` representing minimal, typical, and invalid cases.

## Documentation
- [ ] Draft how-to guide(s) for authoring scenarios and validating inputs.
- [ ] Update README quickstart once new constraints land.

## Open Questions
- Should invalid references be fatal or downgraded to warnings with heuristic fixes?
- How do we version the data contract as fields evolve (semver vs schema tags)?
