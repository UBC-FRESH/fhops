Tree Scene Export
=================

P17.6 exports a deterministic glTF/GLB scene from a tree-scale schedule replay.
The scene contains procedural trees, a flat ground plane, the machine path, and
log nodes for processed trees. It is a portable scene artifact, not a renderer;
video production stays in Blender, Three.js, or another external pipeline.

The phase plan is `notes/tree_scale_simulation_plan.md`.

What is exported
----------------

- ``scene.gltf`` — glTF 2.0 JSON with an embedded base64 buffer.
- ``scene.glb`` — binary glTF with the same scene.
- ``camera_path.json`` — four camera keyframes around the tree bounds.
- ``viewer.html`` — a small Three.js viewer that loads ``scene.gltf``.
- ``scene_manifest.json`` — tree/processed/log counts, LOD, bounds, schedule
  digest, replay identity, files, and caveats.

Trees use a shared procedural mesh per species. Detailed mode has a trunk and
crown; simple mode uses a crown-only mesh. Tree nodes carry ``tree_id``,
``block_id``, species, DBH, height, and whether the tree was processed in the
replay. The ground is a flat plane at the lowest tree elevation, not a DEM.
The machine path is a polyline through processed events. Logs are simple box
nodes; above ``--max-log-nodes`` the log nodes are capped.

CLI
---

.. code-block:: bash

   fhops tree scene scenarios/example/scenario.yaml assignments.csv \
     --out build/tree_scene

Optional controls:

- ``--lod-threshold`` — use simple tree geometry above this tree count;
- ``--max-log-nodes`` — cap individual log nodes;
- ``--obstacle x,y,radius_m`` — repeatable replay obstacle;
- ``--strict`` — refuse when the replay has any discrepancy.

The viewer loads Three.js from a CDN and ``scene.gltf`` from the same directory.
Serve the directory over HTTP for browser use. The glTF/GLB files can also be
opened directly in Blender or another glTF viewer.

Limits
------

- Procedural geometry, not surveyed tree meshes, machine CAD, or point-cloud
  rendering.
- Flat ground plane; no DEM terrain, canopy occlusion, or realistic materials.
- No video encoding and no render in CI.
- The scene is derived from the reference stem and machine models; it inherits
  their caveats.
