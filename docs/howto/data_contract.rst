Data Contract Guide
===================

This guide summarises the structured inputs FHOPS expects when authoring scenarios. It
builds on the ``examples/minitoy`` and ``tests/fixtures/regression`` assets and reflects
recent extensions (mobilisation, geo metadata, crew assignments).

Core Tables (CSV)
-----------------

Each scenario references a set of CSV files. Required columns and notes:

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

Reference `tests/test_contract_validations.py` for examples that exercise these validators.

Authoring Checklist
-------------------

1. Populate required CSV tables with consistent IDs and non-negative numeric values.
2. Supply ``timeline`` and ``mobilisation`` sections when shift scheduling or mobilisation
   costs matter.
3. Use ``crew_assignments`` and ``geo`` only when you have supporting data.
4. Run ``fhops validate <scenario.yaml>`` to confirm the scenario satisfies the contract.

See also :doc:`quickstart` for CLI commands and ``tests/fixtures/regression`` for a
mobilisation-aware example.
