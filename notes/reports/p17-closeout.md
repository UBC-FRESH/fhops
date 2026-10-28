# P17 Tree-Scale Closeout

Date: 2026-10-28

Parent issue: #247

Phase branch: `feature/p17-tree-scale`

Status: P17.1-P17.7 are merged into the phase branch. The final phase PR to
`main` is the remaining maintainer-approval gate.

## Scope delivered

P17 adds a tree-scale execution layer:

1. Producer-neutral tree inventory contract, validator, metadata, and synthetic
   fixture.
2. Scenario pin, block tree map, density/volume-proxy reconciliation, and CLI.
3. Pluggable stem model, reference form-factor volume, bucking, products, and
   block reconciliation.
4. Single-machine/one-block spatial simulation with reach, terrain slope, and
   obstacles.
5. Schedule replay from assignments, tree consumption, leftovers, and
   scheduled-versus-simulated discrepancies.
6. Deterministic glTF/GLB scene export, procedural trees, flat ground, machine
   path, log nodes, LOD, camera keyframes, viewer, and manifest.
7. End-to-end fixture, fail-closed matrix, bounded performance smoke, docs, and
   this closeout.

The block/day MILP remains the planning authority. P17 is not an optimizer
replacement and does not claim that tree-scale replay is statistically superior.

## Merged work

| Task | Issue | Merge commit |
| --- | --- | --- |
| P17.1 inventory contract | #248 | `4a5c3a72` |
| P17.2 pin and block map | #249 | `9acb3ee5` |
| P17.3 stem volume/bucking | #250 | `94df02d1` |
| P17.4 one-machine simulation | #251 | `a0d9b9a4` |
| P17.5 schedule replay | #252 | `7774f627` |
| P17.6 scene export | #253 | `9c4f0d92` |
| P17.7 validation/closeout | #254 | `d294cef0` |

P17.6 was merged through PR #271 and P17.7 through PR #273; the other child PR
links are in the issue history.

## End-to-end fixture

`tests/fixtures/tree_scale/` is a complete synthetic bundle:

- one 1 ha block (`B01`);
- 12 synthetic trees from the P17.1 contract fixture;
- one feller-buncher (`H1`), one landing (`L1`);
- one assignment covering the block;
- block work volume equal to the reference stem model merchantable total.

The integration test copies the fixture, registers the inventory, and runs every
CLI stage:

`tests/tree/test_tree_scale_integration.py`

Observed clean results:

- inventory validation: 12 trees, valid;
- map/stems: no reconciliation warning;
- simulation: 12 processed, 0 unreachable;
- replay: 12 processed, no discrepancies, block status `complete`;
- scene: 12 trees, 12 processed, 68 log nodes, deterministic GLB.

## Fail-closed matrix

| Failure | Evidence | Result |
| --- | --- | --- |
| Map before inventory pin | `test_map_requires_a_pin` | exit 1; no output |
| Inventory references unknown block | `test_register_rejects_unknown_block` | exit 1; scenario unchanged |
| Stale inventory checksum | `test_stale_inventory_checksum_fails_validation` | invalid report; exit 1 |
| Strict stem reconciliation warning | `test_strict_stem_reconciliation_fails` | exit 1; no output |
| Strict replay shortfall | `test_strict_replay_shortfall_fails` | exit 1; no output |

Existing P17.1-P17.6 tests also cover bad CRS, duplicate IDs, non-finite
dimensions, out-of-block trees, missing provenance, unknown machines, unsupported
systems, unreachable trees, and deterministic scene export.

## Verification

- `pytest -q tests/tree`: 58 passed.
- Targeted scene tests: deterministic glTF/GLB bytes, GLB header, tree scale,
  LOD, log cap, and CLI output.
- `ruff format --check src tests`: clean.
- `ruff check src tests`: clean.
- `mypy src`: clean.
- `pre-commit run --all-files`: passed.
- `sphinx-build -b html docs _build/html -W`: build succeeded.
- Full `pytest -q` locally: two pre-existing HiGHS option-error tests fail in
  this environment (`test_highs_option_error_is_reported_as_solver_error`); both
  failures reproduce on `feature/p17-tree-scale` before P17.7 and are unrelated
  to tree-scale code. All 58 `tests/tree` tests pass.

## Bounded performance smoke

Environment: Linux, Python 3.12.3, in-process calls, no solver.

The 12-tree fixture is trivial. For a bounded larger case, the fixture trees were
replicated 50 times (600 trees) with unique IDs and offsets, and block volume/
density scaled accordingly. One machine was simulated with a 1,000 m reach so all
600 stems were processed. Timings are single-run smoke measurements, not a
benchmark claim.

| Stage | Time |
| --- | --- |
| register | 0.044 s |
| map | 0.040 s |
| stems | 0.084 s |
| simulate | 0.237 s |
| replay | 0.160 s |
| scene | 0.315 s |

Scene at 600 trees: `scene.gltf` 718 KB, `scene.glb` 357 KB. The default log cap
was exercised (3,400 source logs capped to 2,000 log nodes).

The seven CLI commands on the 12-tree fixture each took roughly 1.5-1.6 s wall
time including Python process startup. These numbers are not a production-scale
performance guarantee.

## Documentation

- `docs/howto/tree_scale.rst` — complete workflow and outputs.
- `docs/reference/tree_inventory.rst` — contract and pin/map.
- `docs/reference/stem_models.rst` — reference model limits.
- `docs/reference/tree_simulation.rst` — one-machine simulation.
- `docs/reference/tree_replay.rst` — schedule replay.
- `docs/reference/tree_scene.rst` — glTF/GLB, viewer, LOD, camera path.
- `docs/reference/cli.rst` — tree command summary.
- `notes/tree_scale_simulation_plan.md` — decisions and limits.

## Limits and risks

- Current fixture is synthetic. No real LiDAR/ITD/ITC inventory, tree map, or
  operational decision is validated.
- Stem volume/bucking and machine productivity are reference scaffolds, not
  calibrated species-specific models.
- One machine and one block; cross-block travel, landing geometry lookup, and
  multi-machine interactions are deferred.
- Scene geometry is procedural; ground is flat, not a DEM. Rendering/video is
  external. The viewer is interactive but not animated.
- The block/day MILP is not coupled to tree-scale decisions in this phase.

## Approval gate

Do not merge the final P17 phase PR to `main` or close #247 until the maintainer
has reviewed this closeout. P16 issues are out of scope and were not modified.
