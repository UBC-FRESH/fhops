# Synthetic tree inventory fixture

This fixture is a deterministic synthetic `fhops.tree.inventory.v1` inventory for
one 1 ha block (`SYNTH_B01`) in EPSG:3005. It exists to test the tree-inventory
contract, not to represent a real LiDAR-derived tree map.

- `inventory.csv` — 12 synthetic trees with species, DBH, height, crown radius,
  confidence, and tile provenance.
- `inventory.meta.json` — inventory metadata and CSV checksum.
- `block.geojson` — the synthetic block polygon.

The species, dimensions, positions, and provenance are fabricated. Do not use
them as a real tree map or an operational input.
