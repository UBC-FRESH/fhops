Tree-Scale Workflow
===================

P17 adds a tree-scale execution path on top of the normal block/day planning
workflow. FHOPS consumes a producer-neutral individual-tree inventory, pins it
to a scenario, builds block tree maps, derives stem volumes and logs, simulates
one machine, replays an assignments schedule, and exports a deterministic 3D
scene.

The block/day MILP remains the planning authority. Tree-scale replay is an
execution/simulation layer; it does not prove that a schedule is statistically
or operationally superior.

Synthetic fixture
-----------------

``tests/fixtures/tree_scale/`` is a complete synthetic end-to-end fixture:

- one 1 ha block, ``B01``;
- 12 synthetic trees from the P17.1 contract fixture;
- one machine, one landing, and one assignment;
- block work volume set to the reference stem model's merchantable total.

It is synthetic. Do not treat it as a real tree map, machine dataset, or
operational plan. Copy it before registering because registration writes a
``tree_inventory`` section into the scenario YAML.

Run the complete path
---------------------

.. code-block:: bash

   cp -r tests/fixtures/tree_scale /tmp/tree-scale
   cd /tmp/tree-scale

   fhops tree inventory validate tree_inventory/inventory.csv \
     --metadata tree_inventory/inventory.meta.json --block B01

   fhops tree register scenario/scenario.yaml \
     tree_inventory/inventory.csv \
     --metadata tree_inventory/inventory.meta.json

   fhops tree map scenario/scenario.yaml --out map
   fhops tree stems scenario/scenario.yaml --out stems
   fhops tree simulate scenario/scenario.yaml \
     --block B01 --machine H1 --out simulate
   fhops tree replay scenario/scenario.yaml assignments.csv --out replay
   fhops tree scene scenario/scenario.yaml assignments.csv --out scene

Outputs
-------

- ``map/tree_inventory_map.json`` and ``.csv`` — block-tree mapping and
  density/volume reconciliation.
- ``stems/tree_stems.json`` and ``.csv`` — per-tree volumes, logs, products, and
  block totals.
- ``simulate/tree_machine_simulation.json`` and events CSV — one-machine spatial
  processing.
- ``replay/tree_replay.json`` and event/block CSVs — schedule execution,
  consumption, leftovers, and discrepancies.
- ``scene/scene.gltf``, ``scene.glb``, ``camera_path.json``,
  ``scene_manifest.json``, and ``viewer.html`` — deterministic 3D artifact.

Open the scene in Blender or another glTF viewer, or serve the directory on a
free local port and open ``viewer.html``:

.. code-block:: bash

   cd scene
   python3 -m http.server <free-port> --bind 127.0.0.1

The viewer is interactive (orbit/zoom) but static. It contains camera keyframes
but does not play an animation or encode video. The ground is a flat plane, not
a DEM, and the trees/logs are procedural.

Fail-closed behavior
--------------------

Use ``--strict`` where available to turn reconciliation warnings into errors:

.. code-block:: bash

   fhops tree stems scenario/scenario.yaml --strict --out stems
   fhops tree replay scenario/scenario.yaml assignments.csv --strict --out replay
   fhops tree scene scenario/scenario.yaml assignments.csv --strict --out scene

Missing pins, unknown blocks, stale checksums, duplicate IDs, bad CRS, missing
provenance, unreachable trees, and scheduled/simulated volume mismatches are
reported explicitly. The synthetic fail-closed matrix is in
``tests/tree/test_tree_scale_fail_closed.py``.

Limits
------

- One machine and one block per simulation; cross-block travel and multi-machine
  interactions are deferred.
- The stem model, bucking rules, product classes, and machine productivity are
  reference scaffolds, not calibrated operational models.
- No real inventory is bundled. A reviewed producer inventory is a separate data
  gate.
- No video rendering is part of FHOPS.

See :doc:`../reference/tree_inventory`, :doc:`../reference/stem_models`,
:doc:`../reference/tree_simulation`, :doc:`../reference/tree_replay`, and
:doc:`../reference/tree_scene`.
