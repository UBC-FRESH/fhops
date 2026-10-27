Tree Inventory Contract
=======================

FHOPS consumes a producer-neutral individual-tree inventory. It does **not**
perform individual-tree detection, crown segmentation, species classification,
or raw point-cloud processing. The producer (FEMIC, an ITD/ITC pipeline, or a
reviewed tree list) supplies the records; FHOPS validates and references them.

The phase plan is `notes/tree_scale_simulation_plan.md`.

Inventory Format
----------------

The inventory is a UTF-8 CSV with a sidecar JSON metadata file::

   tree_id,block_id,x_m,y_m,elevation_m,species_code,dbh_cm,height_m,\
   crown_radius_m,status,confidence,source_id,source_tile_id,\
   merchantable_height_m,defect,grade_hint
   ST001,SYNTH_B01,881712.0,627512.0,412.0,Fd,28.0,22.0,2.4,live,0.94,\
   synthetic,T01,,,

Required columns are ``tree_id``, ``block_id``, ``x_m``, ``y_m``,
``species_code``, ``dbh_cm``, ``height_m``, ``status``, and ``confidence``.
Optional columns cover elevation, crown radius, source identifiers,
merchantable height, defect, and grade hints. Species codes are preserved as
supplied; FHOPS does not silently normalize or remap them.

Metadata declares the schema version, inventory identity, generation time,
source, producer, method, CRS, units, review state, reviewer, block IDs,
caveats, row count, and optional CSV SHA-256::

   {
     "schema_version": "fhops.tree.inventory.v1",
     "inventory_id": "synthetic-block-001",
     "generated_utc": "2026-10-27T00:00:00+00:00",
     "source_id": "synthetic-tree-fixture",
     "producer": "FHOPS synthetic fixture",
     "method": "Deterministic synthetic point list; not an ITD/ITC run.",
     "crs": "EPSG:3005",
     "units": {
       "x_y": "m",
       "elevation": "m",
       "dbh": "cm",
       "height": "m",
       "crown_radius": "m"
     },
     "review_status": "reviewed",
     "reviewed_by": "fixture-reviewer",
     "block_ids": ["SYNTH_B01"],
     "caveats": ["Synthetic contract fixture; not a real tree map."],
     "tree_count": 12,
     "inventory_sha256": "..."
   }

If ``inventory_sha256`` is present it must match the CSV. If
``review_status`` is ``reviewed``, ``reviewed_by`` is required. Missing
metadata, duplicate tree IDs, unknown blocks, non-finite dimensions, negative
DBH/height/crown values, confidence outside 0–1, or a tree outside the declared
block set fail.

Scenario Pin and Block Map
--------------------------

Register a validated inventory in a scenario without copying it::

   fhops tree register scenarios/example/scenario.yaml \
     tests/fixtures/tree_inventory/synthetic_block/inventory.csv \
     --metadata tests/fixtures/tree_inventory/synthetic_block/inventory.meta.json

The scenario gains an optional ``tree_inventory`` section::

   tree_inventory:
     inventory_id: synthetic-block-001
     inventory_sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
     metadata_sha256: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
     inventory_path: ../../trees/inventory.csv
     metadata_path: ../../trees/inventory.meta.json
     crs: EPSG:3005
     review_status: reviewed
     reviewed_by: reviewer
     source_id: synthetic-tree-fixture
     producer: FHOPS synthetic fixture
     method: Deterministic synthetic point list; not an ITD/ITC run.
     tree_count: 12
     block_ids: [SYNTH_B01]
     caveats:
       - Synthetic contract fixture; not a real tree map.

The pin records both checksums, review state, producer provenance, tree count,
and block memberships. Re-registering the same inventory is idempotent; changing
the inventory or metadata under the same identity is rejected. The inventory is
referenced, not copied.

Map the pinned inventory to blocks and reconcile block evidence::

   fhops tree map scenarios/example/scenario.yaml --out build/tree_map

The command requires a scenario pin. It resolves every tree to a scenario block,
reports blocks without trees, and compares tree count and a crude gross-volume
proxy with ``stem_density_per_ha`` and ``work_required``. The proxy is not
merchantable volume; stem-level volume is P17.3. Use ``--strict`` to refuse when
reconciliation warns. Outputs are ``tree_inventory_map.csv`` and
``tree_inventory_map.json``.

CLI
---

Validate an inventory, optionally against a known block set::

   fhops tree inventory validate tests/fixtures/tree_inventory/synthetic_block/inventory.csv \
     --block SYNTH_B01

The command emits a deterministic JSON validation report and exits non-zero on
an invalid inventory.

Fixture
-------

``tests/fixtures/tree_inventory/synthetic_block`` contains a deterministic
12-tree, 1 ha synthetic block in EPSG:3005. It exists to test the contract. Its
species, dimensions, positions, and provenance are fabricated; it is not a real
LiDAR-derived tree inventory or a tree map.

Limits
------

P17.1 defines and validates only the inventory contract. It does not map trees to
a scenario, derive stem volume or bucking, simulate machines, or export 3D
scenes. The current FEMIC/LidarBC bundle contract has no individual-tree product;
a real tree list must be supplied by a producer and reviewed before any
operational tree map is claimed.
