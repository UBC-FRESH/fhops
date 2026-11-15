# TFL 6 LidarBC Public Fixture

Small public FHOPS scenario built from seven clipped VRI polygons (about 100 ha) in the TFL 6
pilot AOI and the FEMIC bundle `lidarbc-995fb1f771f4d7fe` / `2026.10.0-tfl6-pilot`.

The fixture exercises:

- block and landing slope/CHM support rows at native 1 m resolution;
- a road job with optional road geometry;
- terrain/canopy provenance, bundle/product checksums, and OGL-BC attribution;
- the P14.4 operability assessment (several blocks recommend cable/steep classes but the fixture
  intentionally provides only ground-based machines, so the fallbacks are visible);
- a short schedule smoke solve.

## Data

- `scenario.yaml` — FHOPS scenario, bundle pin, and `lidar_support` rows.
- `blocks.geojson`, `landings.geojson`, `roads.geojson` — EPSG:3005 support geometry.
- `data/` — block, machine, landing, calendar, and productivity tables.
- `provenance.json` — bundle/product checksums, licence, selection, and synthetic-table labels.

Only the LiDAR values and clipped VRI geometry are source data. Machine rates, work volumes
(20 m3/ha), productivity (500 m3 per machine-day), landing capacity, and the road job are synthetic
planning values for a smoke test; they are not a field inventory or a calibrated cost model.

## Regenerate

Install `fhops[lidar]`, then:

```bash
python scripts/build_p14_lidar_fixture.py   --bundle /path/to/lidarbc-995fb1f771f4d7fe   --vri /path/to/vri_aoi.geojson
```

The script validates the written scenario through the normal loader. The committed fixture does
not include the bundle or source rasters.

## Validation

```bash
fhops scenario lidar validate /path/to/bundle
fhops scenario operability assess examples/lidar_tfl6/scenario.yaml
fhops solve-heur examples/lidar_tfl6/scenario.yaml --iters 50 --seed 7
```

## Licence

LidarBC products: Open Government Licence - British Columbia (OGL-BC). The fixture preserves the
bundle licence and source metadata in `provenance.json`. VRI geometry is public BC data; retain
the source attribution when reusing it.
