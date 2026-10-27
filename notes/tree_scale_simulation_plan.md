# Phase 17 — Tree-scale inventory and spatial harvesting simulation

Status: active (2026-10-27)
Parent issue: #247
Branch: `feature/p17-tree-scale`
Roadmap: `ROADMAP.md`, section "Phase 17 — Tree-scale inventory and spatial harvesting simulation"

## Context

FHOPS currently plans at block/day resolution. Its operational MILP and
heuristics assign machines to blocks and shifts, and playback evaluates
block-level production. The LiDAR path (P14) consumes FEMIC LidarBC raster
products as polygon-level terrain/canopy support. It does not consume
individual-tree point clouds, tree lists, crown maps, or stem maps.

The current FEMIC/LidarBC bundle contract has no individual-tree product, and no
tree-level inventory was found in the mounted FHOPS/FEMIC bundle data during
this planning pass. P17.1 must confirm and record the source gap. The initial
fixture is therefore synthetic and must be labelled as such.

Tree-scale simulation could add value that the aspatial model cannot represent:
tree-size mix, species and grade, within-block layout, forwarding distance,
terrain, and machine reach. It could also produce compelling 3D scenes. It does
not automatically make productivity predictions more defensible: individual-tree
detection has occlusion, false-positive, species, and DBH/allometry error. The
tree-scale path must therefore be calibrated and compared against the existing
regressions, not used to replace them by assertion.

## Decision

P17 is a new execution/simulation layer under the existing block/day schedule. It
is a consumer of a producer-neutral tree inventory, not a LiDAR segmentation
pipeline. The existing MILP/heuristic remains the planning authority. Tree-scale
simulation reads a fixed schedule, produces execution evidence, and exposes
discrepancies; it does not silently rewrite the plan.

No raw point-cloud ingestion is required. The producer (FEMIC, an ITD/ITC
pipeline, or a reviewed vendor/student tree list) supplies the tree records.
FHOPS validates and consumes them.

## Data contract

Proposed `fhops.tree.inventory.v1` tree record:

- `tree_id`;
- `block_id`;
- `x_m`, `y_m`, `elevation_m` (or `z_m`);
- `species_code`;
- `dbh_cm`;
- `height_m`;
- `crown_radius_m` (optional);
- `status` (`live`, `dead`, `snag`, `other`);
- `confidence` (0–1);
- `source_id` / `source_tile_id`;
- optional `merchantable_height_m`, `defect`, `grade_hint`.

Inventory metadata declares CRS, units, producer, segmentation method, version,
SHA-256, review state, reviewer, and caveats. The scenario stores a reference and
checksum, not a copy of the tree list.

## Path

```text
external producer tree inventory
  -> P17.1 validate contract + synthetic fixture
  -> P17.2 scenario pin + block tree map + volume reconciliation
  -> P17.3 stem volume / bucking
  -> P17.4 single-machine spatial simulation
  -> P17.5 existing schedule replay at tree scale
  -> P17.6 glTF/GLB scene + viewer/camera path
  -> P17.7 end-to-end validation + closeout
```

## Tasks

### P17.1 — Contract, source audit, synthetic fixture (#248)

Define `fhops.tree.inventory.v1`, validate records and metadata, audit the
available FEMIC/LidarBC products for tree-level content, and add a deterministic
synthetic one-block fixture. No segmentation, stem model, or simulation.

### P17.2 — Scenario pin and block tree map (#249)

Add an optional `tree_inventory` scenario reference, load and checksum the
inventory, resolve every tree to a block, and produce per-block summaries that
reconcile with `work_required`, `volume_per_ha_m3`, and `stem_density_per_ha`.

### P17.3 — Stem volume and bucking (#250)

Define a pluggable stem model, produce gross/merchantable volume and simple
log/product rows, preserve model provenance and uncertainty, and reconcile block
totals. The default synthetic model is explicitly non-operational.

### P17.4 — Single-machine spatial simulation (#251)

Simulate one machine on one block with tree positions, machine position, reach,
terrain, obstacles, deterministic tree selection, and per-tree cycle events. Use
existing FHOPS productivity helpers where they fit. Compare with the block-level
estimate.

### P17.5 — Schedule-coupled replay (#252)

Read an existing assignments CSV/plan, drive the spatial simulator for the
scheduled block-day-machine work, track tree consumption and leftovers, and emit
a discrepancy manifest. The schedule is not changed.

### P17.6 — 3D scene export (#253)

Export deterministic glTF/GLB terrain, trees, machine paths, and logs; add LOD,
a standalone viewer/Blender import, and a camera path. Video rendering remains
external.

### P17.7 — Validation and closeout (#254)

Run the complete synthetic path, cover the fail-closed matrix, measure a bounded
performance case, update docs/roadmap/note/changelog, and write
`notes/reports/p17-closeout.md`. Wait for maintainer approval before merge.

## Acceptance

- A valid inventory loads; every tree maps to exactly one scenario block.
- Bad CRS, duplicate IDs, non-finite dimensions, out-of-block trees, stale
  checksums, and missing provenance refuse with specific errors.
- Tree totals reconcile with block evidence or report an explicit mismatch.
- A single-machine run is deterministic and does not process a tree twice or
  outside reach.
- A schedule replay exposes leftovers and scheduled-vs-simulated differences.
- The scene is deterministic, opens in a standard glTF viewer, and matches the
  replay manifest.
- The synthetic fixture covers success and fail-closed paths.
- FHOPS quality suite and docs build are green.
- No real tree map, operational decision, or regulatory claim is made.

## Limits and risks

- **Data gap:** the current bundles do not contain an individual-tree product.
  The initial fixture is synthetic; a real-data adapter is a separate acceptance
  gate once a producer inventory is supplied.
- **ITD/ITC error:** occlusion, missed trees, false positives, species confusion,
  and DBH allometry. Confidence and provenance are mandatory.
- **Model defensibility:** a generic volume/bucking model is a scaffold, not an
  operational claim. A reviewed species-specific model is a follow-up.
- **Spatial scope:** P17 simulates one machine/system and one block at a time.
  Whole-landscape routing and multi-machine traffic are later work.
- **Visualization cost:** glTF size grows with tree count; LOD and external
  rendering are mandatory. CI does not render video.
- **No optimizer integration:** tree-scale decisions are not fed back into the
  MILP in this phase.

## P17.1 contract decision

The tree inventory is a UTF-8 CSV plus a JSON metadata sidecar. The contract is
`fhops.tree.inventory.v1`; records are validated by
`fhops.tree_inventory.load_tree_inventory` and
`validate_tree_inventory`, with the CLI `fhops tree inventory validate`.

The source audit found no individual-tree product in the current FHOPS consumer
contract or the mounted FEMIC/LidarBC bundle data. The committed fixture
`tests/fixtures/tree_inventory/synthetic_block` is therefore synthetic: 12
fabricated trees in a 1 ha EPSG:3005 block, with explicit metadata and a CSV
checksum. It is a contract fixture, not a real tree map.

The loader validates required columns, duplicate IDs, finite dimensions,
positive DBH/height/crown values, confidence, status, metadata schema, units,
CRS, review metadata, declared block membership, row count, and optional CSV
digest. A real producer inventory and review remain a separate gate.

## P17.2 registration and mapping decision

The scenario pin is a single optional `tree_inventory` section. It records the
inventory and metadata checksums, relative paths, CRS, review state, reviewer,
producer, method, tree count, block memberships, and caveats. The inventory is
referenced, not copied. Re-registering the same identity and checksums is
idempotent; a changed inventory under the same identity is rejected.

`fhops tree map` resolves every tree to a scenario block, reports blocks without
trees, and compares tree count against `stem_density_per_ha` and a **crude
gross-volume proxy** against `work_required`. The proxy (`0.5 × basal area ×
height`) is explicitly not merchantable volume; P17.3 replaces it with a stem
model. The default reconciliation tolerance is 25 percent. `--strict` refuses
warnings. No simulation or 3D export is included.
