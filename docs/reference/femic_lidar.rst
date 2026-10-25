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

Shared Parity
-------------

The FHOPS and WS4 consumer contracts were validated against FEMIC bundle
``lidarbc-995fb1f771f4d7fe`` over seven shared TFL 6 polygons. Slope and CHM
mean/p95 values matched exactly (maximum absolute difference ``0.0``).
