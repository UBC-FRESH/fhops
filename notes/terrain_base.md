# Terrain base with negative heightfields

Issue: #369. Branch: `issue-369-terrain-base-fix`.

## Problem

The replay used the lowest scene tree elevation as the terrain base. Edited
heightfields may contain negative relative heights, so the true base is:

```text
lowest_tree_y - minimum_height
```

Using the lowest tree directly shifted the terrain mesh and retained/overlay
trees down by the negative height minimum, making retained trees appear below
the ground.

## Fix

- If a terrain `base_m` is present, keep using it.
- Otherwise derive the base as `lowest_scene_tree_y - min(heightfield)`.
- Terrain, retained trees, stream clumps, landings, and replay overlays now share
  the scene tree elevation basis.

## Verification

- CTL replay with an edited heightfield containing `-30 m` minimum: retained
  trees align with the terrain surface.
- Existing positive-height and explicit-base projects remain compatible.
