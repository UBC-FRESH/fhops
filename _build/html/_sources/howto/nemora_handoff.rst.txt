Nemora Tree-Inventory Handoff
=============================

FHOPS consumes producer-neutral ``fhops.tree.inventory.v1`` inventories. This
page demonstrates a fixture exported by Nemora ``0.1.0a1``; FHOPS does not
import Nemora at runtime or test time.

Fixture
-------

The committed fixture is under ``examples/nemora_handoff/``:

- ``tree_inventory/tree_inventory.csv`` — 40 synthetic trees, block ``B01``;
- ``tree_inventory/tree_inventory.meta.json`` — checksum, units, provenance;
- ``tree_inventory/provenance.json`` — Nemora version, seed, synthetic input;
- ``scenario/scenario.yaml`` — one-block/one-landing FHOPS scenario.

Validate the inventory:

.. code-block:: bash

   fhops tree inventory validate \
     examples/nemora_handoff/tree_inventory/tree_inventory.csv \
     --metadata examples/nemora_handoff/tree_inventory/tree_inventory.meta.json \
     --block B01

Run the system:

.. code-block:: bash

   fhops tree system examples/nemora_handoff/scenario/scenario.yaml \
     --block B01 --feller H1 --skidder H2 --skidder H3 \
     --processor H5 --loader H4 \
     --truck-capacity 5 --truck-count 1 --landing-capacity 15 \
     --out build/nemora_handoff_system

Boundary
--------

- Nemora owns the producer-side export and synthetic stand generation.
- FHOPS owns validation, pinning, mapping, and tree-scale simulation.
- The fixture is synthetic: not a surveyed stand, real tree map, or operational
  plan.
- No Nemora package is required to validate or run the fixture.
