# Nemora handoff scenario

A compact synthetic scenario that consumes the Nemora-generated tree inventory
in `../tree_inventory/`.

- Block/landing: B01 / L1
- Inventory: `nemora-phase19-handoff`, 40 trees
- Machines: feller H1, skidders H2/H3, processor H5, loader H4
- All data synthetic; this is not an operational plan.

Run:

```bash
fhops tree system examples/nemora_handoff/scenario/scenario.yaml \
  --block B01 --feller H1 --skidder H2 --skidder H3 \
  --processor H5 --loader H4 \
  --truck-capacity 5 --truck-count 1 --landing-capacity 15 \
  --out build/nemora_handoff_system
```
