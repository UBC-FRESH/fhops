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
