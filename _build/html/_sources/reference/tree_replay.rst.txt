Tree-Scale Schedule Replay
==========================

P17.5 replays an existing FHOPS assignments CSV at tree scale. It reads
machine/block/day rows, drives the single-machine simulator, consumes trees
deterministically, and reports scheduled-versus-simulated differences. The
schedule and scenario are never rewritten.

The phase plan is `notes/tree_scale_simulation_plan.md`.

Input
-----

The assignments CSV requires:

- ``machine_id``;
- ``block_id``;
- ``day``.

Optional columns:

- ``shift_id``;
- ``production`` — scheduled merchantable volume for this assignment;
- ``assigned`` — ``0``/``false``/``no`` rows are skipped.

If ``production`` is present and positive, the replay processes trees until that
volume is reached or the machine's daily-hour limit is reached. If it is absent,
the assignment is time-bounded by the machine's ``daily_hours``. A zero scheduled
volume records a ``no_work`` row without consuming trees.

The replay checks that a machine's role belongs to the block's harvest-system
roles when that system is available. Unknown blocks/machines, unsupported
systems, unreachable trees, remaining trees, and under/over production are
recorded explicitly.

CLI
---

.. code-block:: bash

   fhops tree replay scenarios/example/scenario.yaml assignments.csv \
     --out build/tree_replay

Optional circular obstacles use ``--obstacle x,y,radius_m`` and may be repeated.
``--strict`` refuses when any discrepancy is recorded. ``--dry-run`` prints the
manifest without writing files.

Outputs:

- ``tree_replay_events.csv`` — flat assignment/tree events;
- ``tree_replay_blocks.csv`` — block consumption and remaining volume;
- ``tree_replay.json`` — manifest with assignments, blocks, discrepancies,
  schedule digest, model identity, warnings, and caveats.

Limits
------

- Replay is an execution test, not a rescheduling algorithm and not optimizer
  integration.
- Cross-block machine travel is not modeled; each block starts from its first
  remaining tree unless the replay has a position for the same machine/block.
- Machine-level assignments are replayed; full multi-machine traffic,
  forwarding/landing inventory, and system-level interactions are deferred.
- Production targets come from the assignments CSV; if absent, the daily-hour
  limit is the only bound.
- The underlying stem and machine models remain reference scaffolds.
- The replay feeds :doc:`tree_scene` for glTF/GLB export.
