# Stand assets for the FHOPS serious game

`catalog.yaml` selects the three MVP stand polygons. Each GeoJSON is the exact
boundary used by the level viewport and tree placement, stored in EPSG:3005.

## Source layers

- `mkrf_684.geojson`: MKRF `RES_KEY 684` from
  `femic-mkrf-instance/models/mkrf_patchworks_model/spatial/fragments.shp`.
  This is a VRI-derived MKRF patchworks fragment (BEC from the MKRF stand/AU
  assignment table).
- `gavin_3.geojson`: Gavin Lake `BLOCK_ID 3` from
  `femic-afrf-gavinlake-instance/data/legacy_gavinlake/spatial/fragments.shp`.
  This is a VRI-derived Gavin Lake cutblock.
- `kc_57254551.geojson`: Knife Creek `POLYGON_ID 57254551` from
  `femic-afrf-knifecreek-instance/data/inventory/vri_2025_kc.gpkg` (VRI 2025
  R1).

The MKRF and Gavin Lake FEMIC instances currently expose VRI-derived stand
fragments rather than the raw VRI polygon layer. If the game requires raw VRI
polygons for all three forests, those two files must be replaced from the
public VRI with the same stand identifiers and the catalog provenance updated.

## Not yet present

The catalog records stand boundaries and attributes, not the generated tree
lists, landing/road assets, or product prices. Those are separate pinned
artifacts. Do not score a level until its Nemora/PSP inventory and precompute
are complete.
