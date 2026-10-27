Single-Machine Tree Simulation
==============================

P17.4 adds a deterministic single-machine spatial simulation over a pinned tree
inventory. It moves one machine through one block, selects trees by reach, rejects
trees blocked by terrain or circular obstacles, and emits per-tree processing
events. It is a reference execution layer, not a calibrated machine-routing or
physics model.

The phase plan is `notes/tree_scale_simulation_plan.md`.

Model
-----

The simulator:

- starts at an explicit ``(x, y, z)`` point, or at the first tree when no start
  is supplied;
- processes the nearest feasible tree within ``reach_radius_m``;
- when no tree is in reach, moves to an approach point within reach of the
  nearest feasible tree;
- rejects a tree when a circular obstacle contains it or when the absolute
  terrain slope between the current position and the tree exceeds
  ``max_slope_percent``;
- uses the ADV6N10 harvester regression for processing time, with the tree's
  merchantable volume, log count, one stem per cycle, and mean log length;
- uses a constant ``travel_speed_m_per_s`` for moves.

The default values are reach ``10 m``, travel speed ``0.5 m/s``, and maximum
slope ``35%``. They are reference parameters, not field-calibrated settings.

A start point can represent a landing. Automatic landing-geometry lookup is not
part of P17.4; pass the landing coordinates explicitly when that matters.

CLI
---

.. code-block:: bash

   fhops tree simulate scenarios/example/scenario.yaml \
     --block B01 \
     --machine H1 \
     --start-x 881700 --start-y 627500 --start-z 412 \
     --reach-radius 10 \
     --max-slope 35 \
     --out build/tree_machine

Optional circular obstacles use ``--obstacle x,y,radius_m`` and may be repeated.

Outputs:

- ``tree_machine_events.csv`` — one row per visit or unreachable tree;
- ``tree_machine_simulation.json`` — manifest with parameters, events, totals,
  volume reconciliation, warnings, and caveats.

``--dry-run`` prints the manifest without writing files.

Limits
------

- One machine, one block. Multi-machine traffic, forwarding/landing logistics,
  and whole-landscape routing are out of scope.
- Tree positions and elevations come from the inventory; terrain is not a DEM.
- Obstacles are circular exclusions supplied explicitly; FHOPS does not infer
  them from geometry or point clouds.
- Travel is constant speed, not a machine dynamics model.
- Processing time uses an existing harvester regression and the reference stem
  model; it is not a field-validated productivity claim.
- No 3D scene or video is produced in this task.
