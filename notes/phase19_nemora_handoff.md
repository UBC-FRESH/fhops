# Phase 19 plan: Nemora tree-inventory handoff

Parent issue: #300. Branch: `feature/phase19-nemora-handoff`.

## Goal

Prove that a Nemora-generated `fhops.tree.inventory.v1` fixture can be consumed by
the released FHOPS tree-scale workflow without making Nemora a runtime or test
dependency.

## P19.1 Fixture

- Generate a compact deterministic synthetic tree list (~40 trees).
- Export with Nemora 0.1.0a1 (`nemora.export.export_fhops_tree_inventory`).
- Commit CSV + metadata + provenance, with synthetic caveats.
- Validate with FHOPS `validate_tree_inventory` and block `B01`.

## P19.2 Scenario and test

- Add a one-block/one-landing scenario using the fixture.
- Pin the inventory with checksums and block `B01`.
- Run `fhops tree system`.
- Test validation + system run without importing Nemora or using the network.
- Document the producer/consumer boundary and limits.

## P19.3 Close-out

- Run the full FHOPS gates and docs.
- Record fixture provenance and system evidence.
- Decide whether a `1.2.1` release is warranted; no tag/publication without
  separate approval.

## Limits

- Synthetic tree list, not a tree map.
- One block/one landing reference system.
- No operational, financial, or regulatory claim.
