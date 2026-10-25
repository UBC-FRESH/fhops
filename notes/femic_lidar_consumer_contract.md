# FEMIC LidarBC Consumer Contract (P14.1)

FHOPS consumes FEMIC P79 product bundles. It does not discover LidarBC tiles,
download source products, or reimplement terrain/canopy processing.

## Bundle Pin

FHOPS records:

- `bundle_id`
- `bundle_version`
- `manifest_sha256`
- every product `sha256` and `relative_path`

`fhops.scenario.lidar.load_femic_lidar_bundle` validates:

- manifest schema `femic.lidar.product.v1`;
- layout `femic.lidar.bundle.v1`;
- bundle identity and optional expected pin;
- OGL-BC licence;
- source native CRS;
- per-product CRS, resolution, vertical datum, source-tile membership;
- path containment, file size, and SHA-256.

## Scenario Pin and Support

A scenario may also record the pin and aggregated support rows so a run is reproducible without
side files:

```yaml
lidar_products:
  - bundle_id: lidarbc-tfl6-2026.10
    bundle_version: 2026.10.0-tfl6
    manifest_sha256: <64 hex>
    licence_id: OGL-BC
    manifest_path: lidarbc-tfl6-2026.10/manifest.json
lidar_support:
  - support_unit: block
    support_id: B01
    bundle_id: lidarbc-tfl6-2026.10
    bundle_version: 2026.10.0-tfl6
    product: slope
    aggregation: area_weighted_mean
    native_resolution_m: 1.0
    support_area_m2: 12000.0
    valid_pixels: 12000
    slope_percent: 8.2
    canopy_cover_percent: 62.0
    provenance: FEMIC p79.8; 1 m slope/CHM; area-weighted within block polygon
```

Both sections are optional. Block/landing support ids must exist in the scenario, road ids must
exist when `road_construction` is present, support rows must reference a pinned bundle when pins are
present, and duplicate pins/rows are rejected. Existing scenarios without LiDAR fields remain
unchanged.

## Registration Workflow

```bash
fhops scenario lidar validate data/femic/lidarbc-tfl6-2026.10
fhops scenario lidar register scenarios/tfl6/scenario.yaml \
  data/femic/lidarbc-tfl6-2026.10 \
  --expected-bundle-id lidarbc-995fb1f771f4d7fe
```

Registration validates the bundle, checks the scenario `geo.crs` against the product CRS, records
the block-GeoJSON bbox, writes the bundle pin/product checksums/selection, and reloads the scenario
through the normal loader before replacement. `--dry-run` prints the pin without writing. No source
tiles are downloaded.

## Support Mapping

`summarize_femic_lidar_for_polygons` maps a bundle raster to block/landing
support. Polygon CRS must already match the product CRS. The function supports
`mean`, `p95`, `min`, and `max` and never reprojects or resamples.

FHOPS uses polygon means and p95 for harvest-system, operability, and cost
evidence. The support footprint must be recorded by the caller.

## Optional Dependencies

The manifest/checksum validator is stdlib-only. Polygon summaries require
`fhops[lidar]` (`geopandas`, `rasterio`).

## Shared Parity

Validated against FEMIC bundle `lidarbc-995fb1f771f4d7fe`
(`2026.10.0-tfl6-pilot`) over seven TFL 6 AOI polygons. FHOPS and WS4 values
matched exactly (max absolute difference 0.0) for slope/CHM mean and p95.
