# Studio multi-segment road network

Issue: #337. Branch: `issue-337-road-network`.

## Problem

The Studio stored one road polyline (`road.points`). The core terrain router can
consume a `MultiLineString`, but the authoring layer could not create branches
or pass a network through the derived-case handoff.

## Design

- `road.segments` is the current project representation:
  `[{id, label, points: [[x, y], ...]}]`.
- `road_segments(project)` normalizes the model and migrates legacy
  `road.points` to a single `road-main` segment.
- The 2D and 3D editors draw all segments. The road tool appends to the active
  (last) segment; **Shift-click starts a new branch**.
- `materialize_case` exports:
  - `LineString` for one segment;
  - `MultiLineString` for two or more segments.
  The core `TerrainRouter` already accepts both.
- Replay reads the authored segments and draws the road ribbon network, with a
  spur from the landing to the nearest road point.

## Verification

- `test_road_network_exports_multilinestring` covers the GeoJSON handoff and
  manifest segment metadata.
- `node --check` for the 2D, 3D, replay, and viewer bundles.
- Targeted Studio/tree pytest passes.

## Limits

- This slice routes over the authored road geometry; multiple independent
  landings and per-landing machine fleets remain the next slice.
- Branches must be geometrically connected for the core network router to find
  connected paths.

## Closeout

- PR #338 merged to `main` as `e8b1f979e1dd644aec017803576ebe05d802966d`.
- Main CI `41397871126` passed.
- Public demo deployment: `d96183bc`.
- All four live demo projects were regenerated with fresh P25 runs before this
  slice.
- Temporary two-branch project smoke test rendered both roads in 2D with no
  browser errors.
