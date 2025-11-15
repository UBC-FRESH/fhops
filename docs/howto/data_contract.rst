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
      - Optional: ``role``, ``crew``; numeric fields must be non-negative. ``daily_hours`` defaults
        to ``24`` — we assume machines are available around the clock unless explicitly constrained
        by the calendar or shift-level availability. ``operating_cost`` is the machine rental rate in
        $/SMH (scheduled machine hour), i.e., SMH = scheduled hours and PMH = productive hours;
        Lahrsen (2025) productivity coefficients are calibrated in m³/PMH15 (PMH with short delays
        ≤15 min included). Convert to $/m³ post‑hoc using playback outputs or the costing helper.
      - The `fhops dataset inspect-machine` CLI warns when a machine advertises non-24 h
        availability so you can catch accidental edits before shipping datasets.
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

- Blocks reference known landings; harvest-system IDs must exist (see :doc:`../reference/harvest_systems` for defaults).
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
- ``ScheduleLock`` — pre-assign specific machine/block/day combinations (enforced in MIP & SA).
- ``ObjectiveWeights`` — tweak solver objective weighting (production, mobilisation penalties,
  transition counts, optional landing-cap slack penalties).
- Round-the-clock operations — unless you override ``machines.csv`` or the calendar, FHOPS
  expects continuous availability (24 h/day) and only pauses work when you add blackouts,
  downtime sampling, or calendar gaps.

``ObjectiveWeights`` fields are optional; omit any you do not need. For example:

.. code-block:: yaml

   objective_weights:
     production: 1.0
     mobilisation: 0.5
     transitions: 2.0
     landing_slack: 3.0

This configuration maximises production while penalising moves between blocks and soft landing
capacity violations. Setting a weight to ``0`` reverts to the default hard behaviour.

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

Schedule Locking
----------------

Lock a machine to a block on a given day by adding ``locked_assignments``:

.. code-block:: yaml

   locked_assignments:
     - machine_id: YARDER1
       block_id: B12
       day: 5

Any attempt to reassign that machine/day is blocked in both the MIP builder and the SA heuristic.

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
