# Nemora handoff fixture

This directory contains a small synthetic inventory exported by **Nemora
0.1.0a1** through `nemora.export.export_fhops_tree_inventory`.

- Schema: `fhops.tree.inventory.v1`
- Producer: Nemora
- Inventory: `nemora-phase19-handoff`
- Block: `B01`
- Trees: 40
- Seed: 20261030
- Synthetic one-hectare placement: 100 m × 100 m, origin `(0, 0)`
- Review status: `not_reviewed`
- Inventory SHA-256: see `tree_inventory.meta.json`

The input tree list is deterministic synthetic DBH/height/species data. It is
not a surveyed stand, a real tree map, or an operational plan.

## Validate

```bash
fhops tree inventory validate \
  examples/nemora_handoff/tree_inventory/tree_inventory.csv \
  --metadata examples/nemora_handoff/tree_inventory/tree_inventory.meta.json \
  --block B01
```

FHOPS validation does not import Nemora. The fixture is a producer artifact, not
a runtime dependency for FHOPS.
