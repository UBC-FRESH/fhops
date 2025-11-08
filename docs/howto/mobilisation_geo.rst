Mobilisation Geospatial Workflow
================================

This guide explains how to derive inter-block distances for mobilisation costs using GeoJSON
block geometries.

1. Prepare a GeoJSON file with block polygons in a projected CRS (e.g., EPSG:26910 for BC).
   The file must contain a `block_id` column.
2. Compute the distance matrix:

   .. code-block:: bash

      fhops geo distances examples/minitoy/minitoy_blocks.geojson --out examples/minitoy/minitoy_block_distances.csv

3. Reference the generated CSV when populating `MobilisationConfig.distance_csv` **or** place it next
   to the scenario YAML and FHOPS will auto-load it (`<scenario_slug>_block_distances.csv`).
4. Distances are centroid-to-centroid in metres. The mobilisation logic will treat distances below
   the walk threshold as walkable and apply setup/move costs otherwise.
5. CLI commands (`fhops solve-*`, `fhops evaluate`) now report `mobilisation_cost` when mobilisation
   data is present, making it easy to track spend alongside production.

GeoJSON is optional—advanced users may provide precomputed matrices directly. Ensure all data uses
consistent projections to avoid mis-scaled distances.
