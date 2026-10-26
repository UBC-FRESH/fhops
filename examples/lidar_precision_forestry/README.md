# Precision-forestry LiDAR fixture (synthetic values, public AOI subset)

This is a small, redistributable P14.5 example for the FEMIC LidarBC consumer path. It is
**not a production LidarBC extraction** and must not be used for a real harvest-system decision.

## Provenance

- `aoi_demo.geojson` is a 1 km square subset of the public GNN model AOI
  `femic-gnn-instance/data/source/aoi/gnn_full.gpkg` (EPSG:3005).
- `aoi_provenance.json` records the GNN source, the proposed Statement of Intent boundary caveat,
  the source service, the subset bounds, and the synthetic-product caveat.
- `femic_bundle/` is a synthetic `femic.lidar.bundle.v1` fixture with OGL-BC contract metadata,
  native 1 m rasters, `CGVD2013`, and deterministic SHA-256 checksums. The slope/CHM values are
  demonstration values, not measured LidarBC products.
- The FHOPS/WS4 shared-AOI parity evidence belongs to the P14.1 contract and the FEMIC bundle
  referenced in `docs/reference/femic_lidar.rst`; this fixture does not claim new cross-repo parity.

The GNN boundary is a **proposed Statement of Intent boundary**, not a final treaty boundary or
legal title determination. Confirm with Gwa'Sala-'Nakwaxda'xw Nation before public or operational
use.

## Contents

- `scenario.yaml` — two blocks and two landings, with a bundle pin and ten support rows.
- `data/` — the tiny operational tables used by the fixture, plus `ground_fb_skid` assignments.
- `femic_bundle/` — synthetic slope/CHM rasters and manifest.
- `blocks.geojson`, `landings.geojson`, `roads.geojson` — support polygons in EPSG:3005.
- `aoi_demo.geojson`, `aoi_provenance.json` — public AOI subset and provenance.

B01 is classified as **cable** by the advisory rules while the scenario's current system is
`ground_fb_skid`; B02 is **ground** and compatible. This mismatch is intentional: the fixture
exercises the explicit cable flag and fallback/current-system report. It is not a recommendation to
log B01 with the current ground system.

## Commands

```bash
fhops validate examples/lidar_precision_forestry/scenario.yaml
fhops scenario lidar validate examples/lidar_precision_forestry/femic_bundle
fhops scenario lidar operability examples/lidar_precision_forestry/scenario.yaml --json
fhops solve-heur examples/lidar_precision_forestry/scenario.yaml \
  --iters 20 --seed 7 --out /tmp/p14-fixture-assignments.csv
```

Local smoke result (2026-10-26): validation passed; the 20-iteration heuristic solve completed with
objective `-2620.193`, production `937.185 m³`, and zero sequencing violations.

## Limits

- Synthetic raster values; no source-tile discovery or materialization.
- Advisory operability thresholds are planning assumptions, not field-validated rules.
- The AOI subset is public provenance metadata; it is not a reviewed production boundary.
