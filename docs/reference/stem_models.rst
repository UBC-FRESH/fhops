Stem Volume and Bucking
=======================

P17.3 adds a pluggable stem-volume and log-bucking layer for tree inventories.
It turns validated tree records into gross volume, merchantable volume, and log
rows. The current model is a **reference form-factor model**, not a calibrated
operational taper or merchantability system.

The phase plan is `notes/tree_scale_simulation_plan.md`.

Reference Model
---------------

The default model computes:

.. math::

   BA = \frac{\pi}{4}\left(\frac{DBH}{100}\right)^2

   V_{gross} = f \cdot BA \cdot H

   L_{merch} = H_{merch} - h_{stump}

   V_{merch} = V_{gross} \cdot \frac{L_{merch}}{H}

where ``f`` is the form factor, ``H`` is total height, ``H_merch`` is the
merchantable height (or total height when absent), and ``h_stump`` is the stump
height. The stem is bucked into logs of at most ``log_length_m``; log volume is
proportional to length. Logs with DBH at or above ``sawlog_min_dbh_cm`` are
labelled ``sawlog``; smaller trees are labelled ``pulp``. A producer
``grade_hint`` is preserved.

Defaults:

- form factor: ``0.45``;
- stump height: ``0.3 m``;
- log length: ``4.9 m``;
- sawlog threshold: ``20 cm DBH``.

These values are placeholders for the simulation path. They are not a
species-specific volume table, taper equation, or grade recovery model.

Python API
----------

.. code-block:: python

   from fhops.stem import ReferenceStemModel, build_stem_inventory

   model = ReferenceStemModel(log_length_m=4.9)
   stems = build_stem_inventory("scenarios/example/scenario.yaml", model=model)
   print(stems.to_dict()["merchantable_volume_m3"])

``StemModel`` is a protocol; a reviewed model can implement ``evaluate(tree)``
and return a ``StemResult`` with logs. The reference model is only a scaffold.

CLI
---

.. code-block:: bash

   fhops tree stems scenarios/example/scenario.yaml --out build/tree_stems

The command requires a scenario ``tree_inventory`` pin. It evaluates every tree,
writes:

- ``tree_stems.csv`` — one row per bucked log;
- ``tree_stem_blocks.csv`` — one row per block;
- ``tree_stems.json`` — deterministic manifest with tree, log, block, model, and
  caveat data.

``--strict`` refuses when a block's merchantable volume differs from
``work_required`` beyond the reconciliation tolerance. ``--form-factor``,
``--stump-height``, ``--log-length``, and ``--sawlog-min-dbh`` override the
reference model for experiments.

Limits
------

- The reference volume/bucking model is synthetic and non-operational.
- Products and grades are simple placeholders; they are not market recovery.
- Block reconciliation uses ``work_required`` and a relative tolerance; it is a
  screening check, not a field validation.
- P17.3 does not simulate machines or export 3D scenes.
