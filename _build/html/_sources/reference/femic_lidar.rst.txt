FEMIC LidarBC Products
======================

FHOPS consumes versioned FEMIC LidarBC product bundles. It does not run LiDAR
discovery, materialization, terrain compilation, or canopy processing.

Bundle Contract
---------------

A FEMIC bundle contains ``manifest.json``, ``provenance/selection.json``, and
``products/``. FHOPS pins:

- ``bundle_id`` and ``bundle_version``;
- ``manifest_sha256``;
- each product ``sha256`` and ``relative_path``.

``fhops.scenario.lidar.load_femic_lidar_bundle`` validates the manifest,
checksums, OGL-BC licence, native CRS, per-product resolution and vertical
datum, and source-tile membership.

Python Usage
------------

.. code-block:: python

   from pathlib import Path
   from fhops.scenario.lidar import (
       bundle_pin,
       load_femic_lidar_bundle,
       summarize_femic_lidar_for_polygons,
   )

   bundle = load_femic_lidar_bundle(
       Path("data/femic/lidarbc-2026.10.0"),
       expected_bundle_id="lidarbc-995fb1f771f4d7fe",
   )
   pin = bundle_pin(bundle)
   rows = summarize_femic_lidar_for_polygons(
       bundle,
       Path("data/blocks.gpkg"),
       product="slope",
       id_field="block_id",
   )

Polygon summaries require ``fhops[lidar]``. Polygon and product CRS must match;
there is no silent reprojection or resampling.

Scenario Pin and Support
------------------------

A scenario can pin one or more bundle versions and record aggregated support evidence. Both
sections are optional, so existing scenarios remain valid::

   lidar_products:
     - bundle_id: lidarbc-tfl6-2026.10
       bundle_version: 2026.10.0-tfl6
       manifest_sha256: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
       licence_id: OGL-BC
       manifest_path: lidarbc-tfl6-2026.10/manifest.json

   lidar_support:
     - support_unit: block          # block | landing | road
       support_id: B01
       bundle_id: lidarbc-tfl6-2026.10
       bundle_version: 2026.10.0-tfl6
       product: slope
       aggregation: area_weighted_mean
       native_resolution_m: 1.0
       support_area_m2: 12000.0
       valid_pixels: 12000
       slope_percent: 8.2
       aspect_degrees: 135.0
       roughness_m: 0.12
       canopy_cover_percent: 62.0
       canopy_height_m: 24.5
       vertical_structure_index: 0.47
       vertical_structure_class: multi_layer
       provenance: FEMIC p79.8; 1 m slope/CHM; area-weighted within block polygon

Rules:

- ``lidar_support`` block/landing ids must exist in the scenario; road ids must exist when a
  ``road_construction`` table is present;
- support rows must reference a pinned ``bundle_id``/``bundle_version`` when pins are present;
- duplicate pins/support rows are rejected;
- native resolution, aggregation, support area, valid pixels, and provenance record how the FEMIC
  summary was made; FHOPS does not compute or resample those values in P14.1.

Operability Report
------------------

After mapping support rows, report advisory system compatibility::

   fhops scenario lidar operability scenarios/tfl6/scenario.yaml --json

The report classifies each block as ``ground``, ``cable``, or ``helicopter`` from block/landing
slope, roughness, and canopy evidence. It compares the scenario's current ``harvest_system_id``
with the terrain class, recommends a class-compatible registered system, and labels any fallback
source (``block.ground_slope_percent`` or class-average roughness). Move-in, landing, and road cost
multipliers are advisory and are not applied by the solver in P14.4. Thresholds are planning
assumptions, not field-validated rules; see ``notes/p14_operability_validation.md``.

Operator Workflow
-----------------

Validate a delivered bundle without touching a scenario::

   fhops scenario lidar validate data/femic/lidarbc-tfl6-2026.10

Pin it in a scenario AOI::

   fhops scenario lidar register scenarios/tfl6/scenario.yaml \
     data/femic/lidarbc-tfl6-2026.10 \
     --expected-bundle-id lidarbc-995fb1f771f4d7fe

Registration validates the bundle and the scenario, checks that the scenario ``geo.crs`` matches
the bundle product CRS, records the block-GeoJSON AOI bbox when present, writes the bundle pin and
per-product checksums, and reloads the scenario through the normal loader before replacing it.
Use ``--dry-run`` to print the pin without writing. No source tile is downloaded or materialized.

Map native-resolution products to block and landing support::

   fhops scenario lidar map scenarios/tfl6/scenario.yaml \
     data/femic/lidarbc-tfl6-2026.10 \
     --statistic mean \
     --product slope_percent=slope \
     --product canopy_height_m=chm

Known product names (``slope``, ``aspect``, ``roughness``, ``canopy_cover``, ``canopy_height``,
``chm``, ``vertical_structure``) map automatically. Each output row keeps the product name,
native resolution, valid-pixel count, support area (for projected CRS), aggregation, and
provenance. Block/landing polygons must already match the product CRS; ``--roads-geojson`` adds
optional road support. Nothing is resampled. ``--dry-run`` prints rows without writing.

Shared Parity
-------------

The FHOPS and WS4 consumer contracts were validated against FEMIC bundle
``lidarbc-995fb1f771f4d7fe`` over seven shared TFL 6 polygons. Slope and CHM
mean/p95 values matched exactly (maximum absolute difference ``0.0``).

Phase Close-Out
---------------

P14 is complete. The end-to-end run validated the real bundle, mapped the public seven-block TFL 6
fixture (18 support rows, no warnings), classified 5 ground and 2 cable blocks, and returned a
200-iteration smoke-solve objective of ``1434.9`` with ``1717.5 m³`` production and zero sequencing
violations. WS4/FHOPS block slope/CHM parity was ``0.0``; the bundle is 12.8 MiB and the committed
fixture is 35.7 KiB. OGL-BC attribution and bundle/product checksums are preserved in
``examples/lidar_tfl6/provenance.json``.

Reports: ``notes/reports/p14-closeout.md`` and ``notes/reports/p14-validation.json``. Operability
thresholds and cost context remain planning assumptions, not field-validated or calibrated
production constraints.
