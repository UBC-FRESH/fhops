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
     - Optional: ``earliest_start``/``latest_finish`` (defaults 1 / ``num_days``); stand metrics (``avg_stem_size_m3``, ``volume_per_ha_m3``, ``stem_density_per_ha``, ``ground_slope_percent``) plus optional uncertainty columns (``volume_per_ha_m3_sigma``, ``stem_density_per_ha_sigma``) are supported and default to Lahrsen (2025) BC ranges in synthetic bundles. Blocks may also specify ``harvest_system_id`` (must match a registry entry) and ``salvage_processing_mode`` (``standard_mill`` | ``portable_mill`` | ``in_woods_chipping``) so salvage presets and telemetry keep the ADV1N5 portable-mill vs. in-woods-chipping warnings aligned with the scenario data.

   * - ``machines.csv``
     - ``id``
     - Optional: ``role``, ``crew``; numeric fields must be non-negative. ``daily_hours`` defaults
       to ``24`` — we assume machines are available around the clock unless explicitly constrained
       by the calendar or shift-level availability. ``operating_cost`` is the machine rental rate in
       $/SMH (scheduled machine hour), i.e., SMH = scheduled hours and PMH = productive hours;
       Lahrsen (2025) productivity coefficients are calibrated in m³/PMH15 (PMH with short delays
       ≤15 min included). Convert to $/m³ post‑hoc using playback outputs or the costing helper.
       When ``operating_cost`` is omitted or set to ``0`` and a ``role`` is provided, FHOPS looks up
       the default machine-rate entry (owning + operating + optional repair) and auto-fills the
       value during scenario validation. Supply ``repair_usage_hours`` (nearest 5 000 h bucket)
       to pick a different FPInnovations usage class when applying the repair/maintenance allowance;
       omit the field to stick with the default 10 000 h bucket.
       The `fhops dataset inspect-machine` CLI warns when a machine advertises non-24 h
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

Machine-Rate Defaults & Costing Helper
--------------------------------------

FHOPS includes a BC-focused rental-rate catalogue under ``data/machine_rates.json`` to keep
costing consistent across scenarios:

- Each entry records ``machine_name``, ``role``, owning/operating costs ($/SMH), default
  utilisation, move-in allowance, citation, and notes. Baseline values combine Dodson et al.
  (2015) Montana machine-rate data (converted at ~1.33 CAD/USD with diesel ≈ CAD 1.80/L) and
  Hartley & Han (2007) coastal grapple-yarders to match BC market conditions.
- Repair and maintenance allowances come from FPInnovations Advantage Vol. 4 No. 23 (2003).
  The report’s 2002 CAD regression averages are escalated to 2024 CAD using the Statistics
  Canada Machinery & Equipment CPI (Table 18-10-0005-01), giving a cumulative multiplier of
  ≈1.56. FPInnovations reports the allowances at cumulative usage classes of 0–5k, 0–10k,
  0–15k, 0–20k, and 0–25k operating hours; we treat the 10 000 h bucket as the default because
  every machine class has data at that point and it best represents a “typical” fleet age.
  Newer machines (≤5 000 h) and end-of-life machines (≥15 000 h) sit in the neighbouring buckets,
  so supplying ``repair_usage_hours`` lets you scale the allowance up or down using the published
  FPInnovations ratios when a scenario deviates from the baseline. These allowances remain optional
  per role.
- The CLI exposes the defaults via ``fhops dataset estimate-cost``::

      # Deterministic Lahrsen productivity with table defaults
      fhops dataset estimate-cost --machine-role grapple_yarder \
        --avg-stem-size 0.45 --volume-per-ha 320 --stem-density 750 --ground-slope 35

  The command prints the chosen role, source, owning/operating/repair split, utilisation,
  productivity (m³/PMH15), and $/m³. Add ``--include-repair/--exclude-repair`` to toggle the
  FPInnovations allowance or ``--usage-hours`` to select a different usage-class multiplier
  (nearest 5 000 h bucket from Table 2). Supplying ``--dataset <scenario.yaml> --machine <ID>``
  auto-loads the machine’s role, ``operating_cost`` (when already populated), and
  ``repair_usage_hours`` so recurring reports always respect the dataset defaults. Override
  components directly via::

      fhops dataset estimate-cost --machine-role feller_buncher \
  --owning-rate 95 --operating-rate 120 --repair-rate 40 \
  --productivity 30 --utilisation 0.8

- When you also need a road/subgrade allowance, append the TR-28 helper directly to the same command:

  .. code-block:: bash

     fhops dataset estimate-cost --machine-role grapple_yarder \
       --productivity 22 --utilisation 0.85 \
       --road-machine caterpillar_235_hydraulic_backhoe --road-length-m 150

  Supplying ``--road-machine`` (slug or name from ``fhops dataset tr28-subgrade``) together with
  ``--road-length-m`` prints a CPI-adjusted “TR-28 Road Cost Estimate” table after the machine-cost
  summary. Use ``--road-exclude-mobilisation`` when movement is covered elsewhere—the CLI warns in
  either case and cites the soil-protection guidance from FNRB3 (Cat D7H vs. D7G trial) and ADV4N7
  (compaction thresholds). When the scenario already lists road jobs (see below), ``fhops.dataset estimate-cost
  --dataset …`` auto-selects the only row or lets you pick via ``--road-job-id``; attach additional soil warnings by
  referencing ``data/reference/soil_protection_profiles.json`` through ``--road-soil-profile`` (or via the CSV).

- To keep road-building metadata alongside the rest of the scenario, add an optional ``road_construction`` table:

  .. code-block:: text

     id,machine_slug,road_length_m,include_mobilisation,soil_profile_ids
     RC1,caterpillar_235_hydraulic_backhoe,150,True,fnrb3_d7h|adv4n7_compaction

  Reference the file under ``data.road_construction`` in ``scenario.yaml``. Each row requires a unique ``id``, a TR-28 machine slug
  (see ``fhops dataset tr28-subgrade``), the road/subgrade length in metres, and whether the published mobilisation charge should
  be included by default. ``soil_profile_ids`` (pipe- or comma-separated) tie into ``data/reference/soil_protection_profiles.json``
  so the CLI can print structured reminders (ground-pressure multipliers, compaction thresholds, recommended mitigation). When a
  scenario contains exactly one row, ``estimate-cost --dataset ...`` pulls that entry automatically; specify ``--road-job-id RC1``
  if multiple road jobs exist or pass ``--road-machine`` / ``--road-length-m`` to override everything from the command line.

- Supplying ``--rental-rate`` bypasses the lookup for bespoke studies, but ``machines.csv`` rows
  should normally use the curated rates (or CLI recomputed totals) so costing/evaluation tools
  stay aligned.
- `fhops dataset inspect-machine` prints the machine metadata and the same default owning/operating/repair
  breakdown (honouring ``repair_usage_hours``) so you can audit scenario inputs without running a full cost estimate.
  You can also inspect the rental table directly via ``--machine-role`` (e.g., ``fhops dataset inspect-machine
  --machine-role loader_barko450`` dumps the TN-46 Barko 450 live-heel loader rate). Historical Appendix II presets
  such as ``loader_cat966c_tr45``, ``skidder_tr45``, and ``bulldozer_tr45`` are exposed the same way so you can compare
  CPI-normalized 1979 CAD rates against modern entries. When you pair the command with a harvest system such as ``ground_fb_loader_liveheel``, the loader job automatically
  swaps its cost role to ``loader_barko450`` so budgeting outputs stay aligned with the TN-46 preset. Add
  ``--json-out machine.json`` to capture the same payload for automated QA pipelines. Solver telemetry
  (``solve-heur``, ``solve-ils``, ``solve-tabu``, ``eval-playback``) automatically embeds this ``machine_costs`` bundle
  whenever ``--telemetry-log`` is used, so KPI histories and dashboards can trace the assumed repair buckets.

Overriding the defaults follows two common paths:

1. **Quick sensitivity checks** – keep the built-in role but pass overrides to the CLI, e.g.

   .. code-block:: bash

      fhops dataset estimate-cost --machine-role grapple_yarder \
        --owning-rate 185 --operating-rate 260 --repair-rate 50 \
        --avg-stem-size 0.5 --volume-per-ha 280 --stem-density 700 --ground-slope 40

   This keeps the source/role metadata but swaps in your costs for the report/run only.

2. **Persistent dataset changes** – clone ``data/machine_rates.json`` or edit your scenario’s
   ``machines.csv``. For the JSON table, add a new entry (e.g., ``"role": "custom_grapple"``) and
   point ``machines.csv.role`` at that slug; the loader will backfill operating_cost from your
   entry. Alternatively, write the full $/SMH into ``machines.csv.operating_cost`` for the specific
   machine if the rate is project-specific. Both approaches play nicely with the CLI helpers and
   solver defaults.

When authoring datasets set ``machines.csv.operating_cost`` to the all-in rental rate ($/SMH)
for each machine/system. Use the CLI helper (deterministic or distribution-based) to turn
Lahrsen stand descriptors and machine rates into comparable $/m³ for QA, reporting, or solver
inputs.

Skyline Stand Profiles
----------------------

Arnvik (2024) Appendix 5 stand metadata is bundled under
``notes/reference/arnvik_tables/appendix5_stands_normalized.json`` and exposed via the CLI:

- ``fhops dataset appendix5-stands`` lists authors/species and the parsed slope/ground descriptors
  (filter with ``--author``). The parser converts ranges (e.g., ``23 (5-55)%``) and qualitative labels
  (``Level - Erasmus``) into approximate slope percentages.
- ``fhops dataset estimate-cable-skidding`` evaluates the Ünver-Okan (2020) uphill skidding regressions (spruce
  stands in north-east Turkey). Supply either ``--slope-percent`` or a stand ``--profile`` (author name) to pull
  slope defaults directly from Appendix 5, and treat the results as non-BC placeholders unless you calibrate them.
- ``fhops dataset estimate-skyline-productivity`` wraps the Lee et al. (2018), TR-125, and TR-127 regressions, with
  optional ``--tr119-treatment`` multipliers (strip cut / retention levels) so partial-cut scenarios automatically
  apply the published BC productivity and cost offsets. Lee et al. (2018) regressions are small-scale tethered
  yarder studies from South Korea (HAM300), while TR-127 block-specific models (`tr127-block1` … `block6`) use the
  Appendix VII coefficients from the FPInnovations case studies in northwestern BC. TR-112 only publishes descriptive
  productivity tables, so no regression helper is available for that report yet.
- Programmatically, ``fhops.reference.arnvik_appendix5`` exposes dataclasses and helper functions so skyline
  helpers and costing workflows can bind stand descriptors to the new cable productivity models.

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
