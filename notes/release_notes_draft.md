# FHOPS v0.1.0 Release Candidate — Draft Notes

## Highlights
- Phase 1 hardening complete: data contract validation, modular scheduling scaffolding, CI, geospatial intake.
- Phase 2 solver upgrades: shift-indexed MIP/heuristics, mobilisation penalties, harvest system sequencing, CLI presets.
- Phase 3 evaluation stack: deterministic/stochastic playback, KPI expansion, synthetic dataset generator, analytics notebooks + telemetry dashboards.
- Telemetry + tuning harness: persistent JSONL/SQLite store, CLI tuners (random/grid/bayes), comparison/difficulty dashboards, GitHub Pages publishing.

## Installation
- `pip install fhops` (PyPI)
- Development/release verification via Hatch: `hatch run dev:suite`, `hatch run release:build`.

## Breaking Changes / Migration
- Scenario files must declare `schema_version` and can optionally include GeoJSON references (`scenario.geo` / mobilisation config) for auto-loaded distances.
- Objective weights now configurable (`ObjectiveWeights`); mobilisation penalties enabled by default when config present.

## Known Issues / Next
- Hyperparameter tuning sign-off pending final rerun (documenting tuned presets).
- Agentic tuner R&D + DSS/geo UI remain on backlog.
- Release automation (tag-triggered hatch build + publish) to be wired after RC validation.

## Verification
- Lint/type/test/docs suite via Hatch.
- Packaging smoke test: `hatch build` + venv install.
- Telemetry dashboards: https://ubc-fresh.github.io/fhops/reference/dashboards.html
