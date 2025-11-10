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
consistent projections to avoid mis-scaled distances. The sample ``examples/minitoy`` and
``examples/med42`` scenarios now ship with mobilisation configs and distance matrices so you can
experiment immediately; run ``fhops bench suite`` to compare solver performance and inspect the
``kpi_mobilisation_cost`` and ``kpi_mobilisation_cost_by_machine`` columns in the generated summary.

Command Examples
----------------

Solve the medium benchmark with mobilisation enabled and inspect spend:

.. code-block:: bash

   fhops solve-mip examples/med42/scenario.yaml --out tmp/med42_mip.csv
   fhops evaluate examples/med42/scenario.yaml tmp/med42_mip.csv | grep mobilisation_cost

For quick experimentation on the minitoy scenario:

.. code-block:: bash

   fhops solve-heur examples/minitoy/scenario.yaml --out tmp/minitoy_sa.csv --iters 500
   fhops evaluate examples/minitoy/scenario.yaml tmp/minitoy_sa.csv | grep mobilisation_cost

Tooling Notes
-------------

* Work in a projected coordinate system (e.g., UTM zones such as EPSG:32610/26910) so reported
  distances stay in metres. Use ``ogr2ogr``/``gdalwarp`` or QGIS to reproject shapefiles/GeoPackages
  before exporting GeoJSON.
* If you already maintain distance matrices in another system, skip GeoJSON and place the CSV next
  to the scenario YAML (or reference it via ``MobilisationConfig.distance_csv``). The loader will
  prefer inline data over auto-generated filenames.
* Typical workflow:

  1. Export block polygons to GeoJSON with ``block_id`` property.
  2. Run ``fhops geo distances`` to generate the matrix.
  3. Drop the CSV alongside the scenario or set ``mobilisation.distance_csv`` explicitly.
  4. Calibrate machine-specific costs/thresholds using the benchmarking harness.
