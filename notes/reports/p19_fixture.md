# Phase 19 Nemora fixture

Date: 2026-10-30

Phase: P19

Task: P19.1

Status: complete.

## Fixture

- Path: `examples/nemora_handoff/tree_inventory/`
- Producer: Nemora `0.1.0a1`
- Inventory id: `nemora-phase19-handoff`
- Block: `B01`
- Trees: 40
- Species: FD, HW, AT, SW
- Seed: 20261030
- Schema: `fhops.tree.inventory.v1`
- Review status: `not_reviewed`
- Inventory SHA-256: `ef06d3a81230a35c5cd75fb149017f7fe0bbb3bc35a147473e5f31665180cec5`

FHOPS `validate_tree_inventory` accepts the fixture with `block_ids={'B01'}`:
40 trees, 1 block, 4 species, no errors.

## Provenance

- Producer and export function are recorded in `provenance.json`.
- The input list is deterministic synthetic data; no field data.
- Nemora is not a FHOPS runtime or test dependency.

## Limits

- Not a real tree map.
- No operational or regulatory claim.
