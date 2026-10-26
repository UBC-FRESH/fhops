TFL 6 LidarBC Fixture
=====================

``examples/lidar_tfl6`` is a small public FHOPS scenario built from seven clipped VRI polygons
(about 100 ha) in the TFL 6 pilot AOI and FEMIC bundle
``lidarbc-995fb1f771f4d7fe`` / ``2026.10.0-tfl6-pilot``. It is a public example, not a production
dataset or a field inventory.

What It Exercises
-----------------

- Native 1 m block and landing slope/CHM support rows.
- A road construction job with optional road geometry.
- Bundle/product checksums, selection provenance, OGL-BC attribution, and the scenario
  ``lidar_support`` contract.
- The advisory P14.4 ground/cable/helicopter classifier, including explicit mismatches and
  labelled class-average roughness fallbacks.
- A short simulated-annealing schedule smoke test.

Terrain And Canopy Evidence
---------------------------

The block support values are the native-resolution means used by the WS4/FEMIC shared-AOI parity
check. The assessment also compares each block with its landing slope; the class below is the
reported terrain class.

.. list-table::
   :header-rows: 1
   :widths: 18 12 12 12 14 26

   * - Block
     - Work (m³)
     - Slope (%)
     - CHM (m)
     - Class
     - Current system
   * - ``T6_23339490``
     - 108.6
     - 18.09
     - 10.65
     - ground
     - ``ground_fb_skid`` (compatible)
   * - ``T6_23339461``
     - 44.8
     - 51.55
     - 19.20
     - cable
     - ``ground_fb_skid`` (mismatch)
   * - ``T6_23339462``
     - 104.5
     - 19.69
     - 1.08
     - ground
     - ``ground_fb_skid`` (compatible)
   * - ``T6_23339458``
     - 1462.4
     - 22.59
     - 8.70
     - ground
     - ``ground_fb_skid`` (compatible)
   * - ``T6_16625195``
     - 122.5
     - 40.47
     - 13.97
     - cable
     - ``ground_fb_skid`` (mismatch)
   * - ``T6_16624698``
     - 132.6
     - 22.01
     - 1.99
     - ground
     - ``ground_fb_skid`` (compatible)
   * - ``T6_19212607``
     - 24.7
     - 27.32
     - 16.54
     - ground
     - ``ground_fb_skid`` (compatible)

Work volumes, machine rates (500 m³ per machine-day), landing capacity, and the road job are
synthetic smoke-test values. Only the LiDAR values and clipped VRI geometry are source data.

Files
-----

``examples/lidar_tfl6`` contains:

- ``scenario.yaml``: bundle pin, support rows, and scenario metadata;
- ``blocks.geojson``, ``landings.geojson``, ``roads.geojson``: EPSG:3005 support geometry;
- ``data/``: block, machine, landing, calendar, and productivity tables;
- ``provenance.json``: bundle/product checksums, licence, selection, and synthetic-table labels;
- ``README.md``: operator summary.

Commands
--------

.. code-block:: bash

   fhops scenario lidar validate /path/to/lidarbc-995fb1f771f4d7fe
   fhops scenario lidar operability examples/lidar_tfl6/scenario.yaml --json
   fhops solve-heur examples/lidar_tfl6/scenario.yaml \
     --out /tmp/tfl6-assignments.csv --iters 200 --seed 7

The P14.5 smoke solve returned objective ``1434.900``, production ``1717.5 m³``, three completed
blocks, and zero sequencing violations. This is a schedule smoke test, not an optimality or
financial-feasibility claim.

Regeneration
------------

The fixture can be regenerated from the bundle and clipped VRI layer:

.. code-block:: bash

   python scripts/build_p14_lidar_fixture.py \
     --bundle /path/to/lidarbc-995fb1f771f4d7fe \
     --vri /path/to/vri_aoi.geojson

The script writes deterministic tables, support rows, provenance, and README, then validates the
scenario through the normal FHOPS loader. It requires ``fhops[lidar]``.

Parity And Limits
-----------------

The seven block slope/CHM means match the WS4 P52 / FEMIC P79.9 shared-AOI rows to the recorded
six-decimal precision (maximum absolute difference ``0.0``). The fixture is not a provincial
scenario, does not include the source rasters or bundle, and does not claim field accuracy,
calibrated cost, or production readiness. Cable/helicopter recommendations stay advisory; the
fixture intentionally supplies only ground-based machines so the mismatch is visible.

Performance, Storage, And Licence
---------------------------------

Measured on 2026-10-26 with ``fhops[lidar]`` installed:

- fixture apparent size: ``35,740`` bytes across 11 files;
- scenario load: ``0.037 s``;
- advisory operability report: ``0.0025 s``;
- SA smoke solve (20 iterations): ``0.080 s`` in-process, ``1.79 s`` end-to-end CLI,
  ~147 MB peak RSS;
- full 200-iteration CLI smoke: objective ``1434.900``, production ``1717.5 m³``, zero sequencing
  violations.

The FEMIC bundle and source rasters are not committed; the fixture carries their checksums,
selection metadata, and OGL-BC attribution in ``provenance.json``. The planning tables are
synthetic and labelled. See ``notes/reports/p14.5-fixture-validation.md`` and
``notes/reports/p14-closeout.md``.
