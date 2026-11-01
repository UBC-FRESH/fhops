# Studio terrain elevation alignment

Issue: #332. Branch: `issue-332-terrain-elevation`.

## Problem

After terrain edits, replay trees, retained trees, landings, and other ground
objects could appear below or above the rendered terrain. X/Y placement was
correct, but the vertical elevation basis was inconsistent.

## Root cause

`_write_project_inventory` accepted an `elevation_fn` but wrote the original
`tree.elevation_m`. The derived DEM used the edited heightfield, so the scene
GLTF tree elevations and the terrain mesh disagreed. Retained-tree and landing
overlays sampled the edited terrain, making the mismatch visible.

A second display issue was that the replay terrain mesh only covered the block
bounds, while the derived DEM and the landing/road could extend beyond it.

## Changes

- Derived inventory rows now use `elevation_fn(x, y)` when terrain edits exist.
- Replay terrain bounds are expanded to include the block, landing, road, and a
  margin. The edited heightfield is resampled onto the expanded grid so
  landings, machines, retained trees, and clumps share the displayed terrain.
- Added a regression test asserting derived inventory elevations match
  `_terrain_elevation`.

## Verification

- New test: `test_materialized_tree_elevations_follow_terrain`.
- Reprocessed the Gavin project in a temporary Studio instance:
  - new scene tree y range: `751.74 … 787.75`;
  - edited terrain range: `-30 … 6.48` with base `781.74`, i.e. `751.74 … 788.22`;
  - landing and road now remain on the extended terrain mesh.
- Browser smoke test: retained cluster, machines, landing, and timeline all
  render on the same terrain surface.

## Follow-up

Existing runs keep their old scene elevations. Rerun a project after this fix to
regenerate its scene and replay.
