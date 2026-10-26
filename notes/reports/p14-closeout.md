# P14 close-out — Consume FEMIC-compiled LidarBC products

Date: 2026-10-26
Parent issue: #188
Phase branch: `feature/phase14-lidar-products`
Evidence commits:
- P14.1 `81aae50` (PR #202)
- P14.2 `54545d7` (PR #203)
- P14.3 `94c577d` (PR #204)
- P14.4 `b9cdf56` (PR #205)
- P14.5 `9026968` (PR #206)
- P14.6 close-out commit follows this report

## Outcome

FHOPS is now a clean consumer of FEMIC-compiled LidarBC products. It pins a versioned bundle,
validates manifest/checksums/licence/CRS/native resolution/vertical datum/lineage, maps native
terrain and canopy rasters to block/landing/road support, records explicit support/aggregation
provenance, and reports advisory ground/cable/helicopter operability plus labelled fallbacks. It
does not discover, download, materialize, or reprocess source LiDAR.

## Delivered path

| Task | Evidence |
|---|---|
| P14.1 Consumer contract (`FemicLidarBundle`, checksums, pins, polygon summaries, scenario pin/support) | `81aae50`, `notes/femic_lidar_consumer_contract.md`, `docs/reference/femic_lidar.rst` |
| P14.2 Registration (`fhops scenario lidar validate|register`, AOI/CRS checks, stable pin) | `54545d7` |
| P14.3 Mapping (`fhops scenario lidar map`, native-resolution support rows) | `94c577d` |
| P14.4 Advisory operability (`ground/cable/helicopter`, compatibility, fallbacks, cost context) | `b9cdf56`, `notes/p14_operability_validation.md` |
| P14.5 Public TFL 6 fixture and WS4/FEMIC parity | `9026968`, `examples/lidar_tfl6`, `notes/reports/p14.5-fixture-validation.md` |
| P14.6 Validation, limits, docs, close-out | this report |

## Validation evidence

- **Cross-repo parity:** seven TFL 6 block slope/CHM means match WS4 P52 / FEMIC P79.9 to the
  committed six-decimal precision; maximum absolute difference `0.0`.
- **Fixture:** `examples/lidar_tfl6` validates and reloads through the normal loader; seven blocks,
  one landing, one road job, 18 support rows, OGL-BC provenance, and checksums recorded.
- **Operability:** two blocks classify as cable and report the current ground-system mismatch; five
  are ground-compatible; missing roughness uses the explicit `class_average_roughness` fallback.
- **Smoke solve:** 200-iteration SA returned objective `1434.900`, production `1717.5 m³`, three
  completed blocks, zero sequencing violations.
- **Performance:** fixture apparent size 35,740 bytes / 11 files; scenario load 0.037 s; operability
  0.0025 s; 20-iteration in-process solve 0.080 s; end-to-end CLI 1.79 s / ~147 MB peak RSS.
- **Tests:** `pytest -q tests/scenario` passes with `fhops[lidar]`; full `pytest` keeps only the two
  pre-existing HiGHS option-error failures. Ruff, mypy, and Sphinx are clean.

## Licence and attribution

The fixture carries OGL-BC licence and attribution from the FEMIC bundle/selection metadata in
`examples/lidar_tfl6/provenance.json` and the scenario pin. Source rasters and the bundle are not
committed; FHOPS does not redistribute them. Reports and exports should preserve the OGL-BC
attribution.

## Deviations and limits

- Planning tables in the public fixture (work volumes, machine rates, landing capacity, road values)
  are synthetic and labelled; they are not field inventory or calibrated costs.
- The FEMIC bundle is external; the fixture stores support values and checksums, not source rasters.
- Operability thresholds are planning assumptions until field-validated.
- Aspect is reported but does not change the operability class.
- Move-in/landing/road cost multipliers are advisory and are not applied by the solver in P14.
- No province-wide scenario, production release, or financial-feasibility claim.

## Validation fix included

End-to-end fixture work exposed a repeated-edit bug in the top-level YAML list-section writer:
column-zero list items (`lidar_support`, `locked_assignments`) were not consumed, so a second edit
could duplicate the old list. P14.6 fixes the writer in the scenario and web editing paths and adds
regression tests for repeated lidar mapping and repeated lock edits.

## Follow-ups

- Field-validate operability thresholds and aspect rules.
- Apply defensible cost multipliers only after calibration.
- Add `--overlay` / authenticated data-product flows if FEMIC publishes them.
- Keep source bundle distribution and OGL-BC attribution under review.
