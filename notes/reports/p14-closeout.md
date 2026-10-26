# P14 Close-Out: Consume FEMIC-Compiled LidarBC Products

Phase: P14 / `#188`
Branch: `feature/p14.6-closeout` (based on `main`)
Status: complete after PR merge
Upstream producer: FEMIC P79 (`UBC-FRESH/femic#211`)
Bundle: `lidarbc-995fb1f771f4d7fe` / `2026.10.0-tfl6-pilot`

## Outcome

FHOPS now consumes versioned FEMIC LidarBC bundles without rediscovering or re-materializing LiDAR:

- P14.1 added the stdlib-only bundle contract, checksum/licence/CRS/resolution/vertical-datum/
  tile validation, polygon summaries, and optional `lidar_products`/`lidar_support` scenario
  sections.
- P14.2 added scenario AOI registration with stable bundle/manifest/product pins, AOI bbox,
  selection provenance, CRS compatibility, dry-run, and explicit failure modes.
- P14.3 added `fhops scenario lidar map` for native-resolution slope/CHM/terrain/canopy support
  over block, landing, and optional road polygons.
- P14.4 added advisory ground/cable/helicopter operability classification from block/landing
  evidence, explicit fallbacks, and advisory move-in/landing/road context.
- P14.5 added the public `examples/lidar_tfl6` fixture with seven clipped VRI blocks, landing/road
  context, provenance, OGL-BC attribution, regeneration script, and smoke solve.
- P14.6 validated the full path, recorded parity/storage/licence evidence, and closed the phase.

## End-To-End Validation

`notes/reports/p14-validation.json` records the run:

1. Validate the real bundle: `is_valid: true`.
2. Map the seven-block fixture through P14.3 with the real bundle and road geometry: 18 support
   rows, 0 warnings.
3. Run P14.4 operability: 7 blocks; 5 ground, 2 cable; the ground-only fixture exposes the cable
   mismatch.
4. Run a 200-iteration SA smoke solve: objective `1434.9`, production `1717.5 m³`, 26 assigned
   slots, 0 sequencing violations.

Measured timings:

| Step | Seconds |
| --- | ---: |
| Bundle validation | 0.043 |
| P14.3 mapping | 0.598 |
| P14.4 operability | 0.027 |
| 200-iteration SA solve | 0.633 |

Storage:

- bundle: 13,406,981 bytes (about 12.8 MiB);
- committed fixture: 35,740 bytes;
- fixture support rows: 18.

## Cross-Repo Parity

The fixture block slope/CHM means match the WS4 P52 / FEMIC P79.9 shared-AOI rows to the committed
six-decimal precision. Maximum absolute difference: `0.0` (tolerance `1e-9` in the upstream
records).

## Licence And Attribution

- Source licence: OGL-BC.
- Licence URL: https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc
- Source: LidarBC Open LiDAR Data Portal / BC Data Catalogue.
- Bundle/product checksums, selection, native CRS, resolution, and vertical datum are preserved in
  `examples/lidar_tfl6/provenance.json`.
- No source tile is downloaded by FHOPS and no full provincial mirror is created.

## Issue Found And Fixed During Close-Out

Repeated `scenario lidar register` or `scenario lidar map` could duplicate top-level YAML sections
because the writer stopped at unindented `yaml.safe_dump` list items. The P14.6 validation run hit
this while re-mapping the fixture. Fixed in `lidar_registration._replace_top_level_section` with
idempotent registration and remapping regression tests.

## Verification

- Full `pytest` -> green in this environment.
- `pytest -q tests/scenario` -> green with the optional LiDAR dependencies.
- `ruff format --check`, `ruff check`, `mypy src`, `sphinx-build -b html docs _build/html -W` ->
  clean.
- Fixture reloads through the normal loader and the smoke solve runs.
- Real bundle validation and mapping run recorded in `notes/reports/p14-validation.json`.

## Limitations

- One small TFL 6 AOI (seven polygons, about 100 ha), not a provincial or TFL-wide scenario.
- Fixture machine rates, work volumes, landing capacity, and road job are synthetic planning values.
- Operability thresholds and cost context are planning assumptions, not field-validated rules or
  calibrated financial multipliers.
- No individual-tree segmentation, field-accuracy claim, production dataset switch, release, or
  tag.
- The FEMIC bundle and source rasters are not committed; the fixture is regenerated from a local
  bundle and VRI layer.

## Close-Out

P14 is complete. Future work should validate operability thresholds and cost context against field
and price data before using them as production constraints. The public fixture is the reproducible
starting point for that work.
