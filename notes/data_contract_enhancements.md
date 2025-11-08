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
- [x] Audit existing `fhops.core` models for missing constraints (e.g., non-negative work, horizon bounds).
  - Enforced non-negative checks across blocks, machines, landings, calendar availability flags, and production rates.
  - Added scenario-level cross validation for horizon bounds, foreign key consistency, and mobilisation distance references.
- [x] Introduce shift calendar models (per-shift durations, blackout dates, weekly rollups). *(TimelineConfig added; scheduling integration pending usage.)*
- [x] Introduce mobilisation schema (machine parameters, block distances). *(MobilisationConfig added; needs wiring into optimisation.)*
- [x] Add schema-level validators ensuring linked IDs exist across CSV inputs (blocks↔systems↔machines↔workers).
  - Cross-checks now cover block→landing, production/calendars→machines, harvest-system IDs, mobilisation distances, and mobilisation machine parameters. Crew/worker mapping remains future work.
- [x] Introduce typed helpers for optional extras (geo metadata, crew assignments).
  - Added `GeoMetadata` and `CrewAssignment` models to the scenario contract, with validation ensuring machine linkage and duplicate prevention.
- [x] Document data contract extensions in Sphinx (`docs/howto/data_contract.rst`).
- [x] Specify GeoJSON ingestion schema (accepted CRS, required block properties) and distance computation workflow. *(Documented in `docs/howto/data_contract.rst`, referencing `fhops geo distances` workflow and CRS guidance.)*

## Tests & Tooling
- [x] Property-based or parametrised tests covering edge-case scenarios. *(Added parametrised coverage in `tests/test_contract_edge_cases.py` for negative values, horizon violations, mobilisation/crew mismatches.)*
- [ ] Regression fixtures under `tests/data/` representing minimal, typical, and invalid cases.

## Documentation
- [ ] Draft how-to guide(s) for authoring scenarios and validating inputs.
- [ ] Update README quickstart once new constraints land.

## Open Questions
- Should invalid references be fatal or downgraded to warnings with heuristic fixes?
- How do we version the data contract as fields evolve (semver vs schema tags)?
