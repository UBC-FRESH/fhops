Precision-forestry LiDAR fixture
================================

``examples/lidar_precision_forestry/`` is a small synthetic P14.5 example that exercises the FEMIC
LidarBC consumer path: bundle pin/checksums, native-resolution support mapping, advisory operability,
landing/road context, validation, and a heuristic smoke solve.

It is **not a production LidarBC extraction**. The public boundary is the GNN model AOI from
``UBC-FRESH/femic-gnn-instance`` (``data/source/aoi/gnn_full.gpkg``), represented by a 1 km subset in
``aoi_demo.geojson`` and recorded in ``aoi_provenance.json``. The boundary is a proposed Statement of
Intent boundary, not a final treaty boundary or legal title determination. Confirm with
Gwa'Sala-'Nakwaxda'xw Nation before public or operational use.

Provenance and values
---------------------

- AOI: GNN proposed SOI/model AOI subset, EPSG:3005, source service and caveat in
  ``aoi_provenance.json``.
- Products: synthetic 1 m slope/CHM rasters in ``femic_bundle/`` with ``CGVD2013`` and OGL-BC
  contract metadata, deterministic SHA-256 checksums, and explicit synthetic lineage.
- Scenario: two tiny blocks/landings, a bundle pin, and ten block/landing/road support rows.
- B01 is intentionally classified as cable while the current system is ``ground_fb_skid``; B02 is
  ground and compatible. This demonstrates the explicit cable flag and fallback/current-system
  report; it is not a harvest recommendation.
- The FHOPS/WS4 shared-AOI parity evidence belongs to the P14.1 contract and the FEMIC bundle
  referenced in :doc:`../reference/femic_lidar`; this fixture makes no new cross-repo parity claim.

Commands
--------

.. code-block:: bash

   fhops validate examples/lidar_precision_forestry/scenario.yaml
   fhops scenario lidar validate examples/lidar_precision_forestry/femic_bundle
   fhops scenario lidar operability examples/lidar_precision_forestry/scenario.yaml --json
   fhops solve-heur examples/lidar_precision_forestry/scenario.yaml \
     --iters 20 --seed 7 --out /tmp/p14-fixture-assignments.csv

Local smoke result (2026-10-26): validation passed; the 20-iteration heuristic solve completed with
objective ``-2620.193``, production ``937.185 m³``, and zero sequencing violations.

Limits
------

- Synthetic raster values; no LiDAR discovery, materialization, or source-tile download.
- Advisory operability thresholds are planning assumptions, not field-validated rules.
- The AOI subset is public provenance metadata, not a reviewed production boundary.
