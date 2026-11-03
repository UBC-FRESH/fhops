# Terrain base with negative heightfields

Issue: #369. Branch: `issue-369-terrain-base-fix`.

## Problem

The replay used inconsistent terrain bases:

1. the lowest scene tree elevation was treated as the base, even though edited
   heightfields can contain negative relative heights;
2. `applyTerrain` reset `baseElevation` to the terrain height at the block
   centre, which corrupted the elevation basis used by retained/overlay trees
   rendered afterward.

With a heightfield minimum of `-30 m`, terrain and retained trees were shifted
down relative to the scene trees.

## Fix

- Replay terrain data carries the project `base_m` and the original source
  heightfield minimum.
- The base fallback is `lowest_scene_tree_y - min(source_heightfield)` when no
  explicit base exists.
- `applyTerrain` no longer rewrites `baseElevation` after placing the terrain
  mesh.
- Terrain, retained trees, clumps, landings, and overlays now share one
  elevation basis.

## Verification

- CTL replay with a `-30 m` heightfield minimum: `baseElevation` is `781.74`,
  matching `terrain.base_m`; retained-tree bases sit on the terrain.
- Existing explicit-base projects remain compatible.
