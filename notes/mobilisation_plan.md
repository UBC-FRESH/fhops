# Mobilisation & Setup Cost Plan

Date: 2025-11-07
Status: Draft — pending modular reorganisation.

## Objectives
- Model machine movement and block setup costs informed by distance thresholds and per-machine walk costs.
- Integrate mobilisation costs into both MIP and heuristic solvers without regressing existing behaviour.
- Surface mobilisation configuration (distance thresholds, per-metre walk costs, setup fees) in the scenario contract and CLI.

## Planned Tasks
- [x] Extend scenario data contract with distance matrices or geometry hooks for blocks/landings. *(MobilisationConfig + BlockDistance scaffolded.)*
- [x] Define mobilisation parameters per machine/system (walk cost per metre, setup cost, threshold distance). *(MachineMobilisation added.)*
- [x] Implement mobilisation penalty terms in Pyomo (`optimization/mip/builder.py`). *(Setup-cost deduction wired into objective.)*
- [x] Add heuristic loss penalties mirroring the MIP logic. *(SA evaluator subtracts setup cost per assignment.)*
- [x] Update evaluation metrics to report mobilisation spend. *(KPI module exposes `mobilisation_cost`; benchmark harness validates non-zero spend).*
- [x] Design geospatial ingestion path (GeoJSON baseline) to derive inter-block distances and persist them in `MobilisationConfig`.
- [x] Provide CLI helper to compute distance matrices from block geometries (projected CRS, configurable unit conversions). *(Prototype via `fhops geo distances`; loader now validates GeoJSON inputs.)*
- [x] Extend mobilisation calibration to the large84 benchmark scenario (generated landing-aware distance matrix, inline mobilisation config, docs updated).

## Tests
- [x] Fixture scenarios with known mobilisation costs (short vs long moves). *(See `tests/test_mobilisation.py`.)*
- [x] Regression tests confirming solver outputs incorporate mobilisation charges. *(Harness smoke test asserts SA mobilisation cost baseline for minitoy.)*
- [x] Integration test covering GeoJSON ingest → distance matrix generation. *(See `tests/test_geospatial_distances.py`.)*

## Documentation
- [x] Sphinx how-to explaining mobilisation configuration and cost outcomes. *(Updated `docs/howto/mobilisation_geo.rst` with calibration guidance and benchmark references.)*
- [x] CLI examples (`fhops solve-mip --mobilisation-config ...`). *(Added mobilisation-focused commands in the mobilisation how-to and CLI reference.)*
- [x] GeoJSON ingestion guide (projection requirements, recommended tooling, optional matrix fallback).

## Open Questions
- Preferred baseline format: GeoJSON vs shapefile vs manual matrix? *(Initial proposal: GeoJSON in UTM/provincial projection; accept precomputed matrix as alternate path.)*
- How to handle mobilisation downtime (time penalty) vs pure cost?
