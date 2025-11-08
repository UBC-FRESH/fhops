Data Contract Guide
===================

This guide summarises the structured inputs FHOPS expects when authoring scenarios. It
builds on the ``examples/minitoy`` and ``tests/fixtures/regression`` assets and reflects
recent extensions (mobilisation, geo metadata, crew assignments).

Core Tables (CSV)
-----------------

Each scenario references a set of CSV files. Required columns and notes:

- ``schema_version``: Contract version tag (currently `1.0.0`).

.. list-table::
   :header-rows: 1

   * - Table
     - Required Columns
     - Notes
   * - ``blocks.csv``
     - ``id``, ``landing_id``, ``work_required``
     - Optional: ``earliest_start``/``latest_finish`` (defaults 1 / ``num_days``)
   * - ``machines.csv``
     - ``id``
     - Optional: ``role``, ``crew``; numeric fields must be non-negative
   * - ``landings.csv``
     - ``id``
     - ``daily_capacity`` defaults to 2, must be ≥ 0
   * - ``calendar.csv``
     - ``machine_id``, ``day``
     - ``available`` ∈ {0,1}; days must lie within ``num_days``
   * - ``production_rates.csv``
     - ``machine_id``, ``block_id``, ``rate``
     - ``rate`` ≥ 0; IDs must exist in machines/blocks

Cross References & Validators
------------------------------

The Pydantic models enforce consistency:

- Blocks reference known landings; harvest-system IDs must exist.
- Calendar and production rates must reference defined machines/blocks and lie within the
  scenario horizon.
- Mobilisation distances must reference known blocks; mobilisation parameters must reference
  known machines.
- Crew assignments (optional) require unique crew IDs and valid machine IDs.

Optional Extras
---------------

Recent helpers enable richer metadata:

- ``MobilisationConfig`` — per-machine mobilisation costs and block distance matrices.
- ``GeoMetadata`` — optional GeoJSON paths and CRS tags for blocks/landings.
- ``CrewAssignment`` — map crew identifiers to machines/roles for downstream planners.
- ``TimelineConfig`` — shift definitions and blackout windows controlling daily availability.

Reference `tests/test_contract_validations.py` for examples that exercise these validators.

Timeline Example
----------------

Add a top-level ``timeline`` block in your scenario YAML to describe shifts and blackouts:

.. code-block:: yaml

   timeline:
     shifts:
       - name: day
         hours: 10
         shifts_per_day: 1
     blackouts:
       - start_day: 5
         end_day: 7
         reason: wildfire risk
     days_per_week: 5

The loader converts this into a ``TimelineConfig`` instance available via ``scenario.timeline``.

GeoJSON Ingestion & Distances
-----------------------------

When supplying block or landing geometries:

- Provide GeoJSON files with a ``FeatureCollection`` containing polygon features.
- Each feature must include an ``id`` or ``properties.id`` matching the block/landing IDs
  defined in the CSV tables.
- Use a projected CRS suitable for distance calculations; FHOPS defaults to
  ``EPSG:3005`` (BC Albers) but any metre-based CRS is acceptable when specified via
  ``geo.crs``.
- Store relative paths in ``GeoMetadata.block_geojson`` / ``landing_geojson`` so the CLI
  tooling can locate the files.

To generate mobilisation distances from geometries, run:

.. code-block:: bash

   fhops geo distances --blocks blocks.geojson --out mobilisation_distances.csv

The command computes centroid-to-centroid distances (in metres) respecting the CRS. The
resulting CSV aligns with the ``MobilisationConfig`` distance format and can be referenced
under ``scenario.data.mobilisation_distances``.

Authoring Checklist
-------------------

1. Populate required CSV tables with consistent IDs and non-negative numeric values.
2. Supply ``timeline`` and ``mobilisation`` sections when shift scheduling or mobilisation
   costs matter.
3. Use ``crew_assignments`` and ``geo`` only when you have supporting data.
4. Run ``fhops validate <scenario.yaml>`` to confirm the scenario satisfies the contract.

Fixture Gallery
---------------

- ``tests/data/minimal`` — smallest possible scenario for smoke-testing the loader.
- ``tests/data/typical`` — multi-block example with mobilisation distances and harvest system IDs.
- ``tests/data/invalid`` — intentionally malformed inputs that surface validation errors.

See also :doc:`quickstart` for CLI commands and ``tests/fixtures/regression`` for a
mobilisation-aware example.
