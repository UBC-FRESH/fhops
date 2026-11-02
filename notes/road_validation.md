# Road-network validation and grade-aware routing

Issue: #360. Branch: `issue-360-road-validation`.

## Changes

- Studio computes `road_network_validation(project)`:
  - segments that intersect at endpoints or interiors are connected,
  - disconnected components produce a warning,
  - landing distance to the nearest road segment is reported,
  - runs are blocked when the network has multiple disconnected components.
- The 2D Studio shows a road-check banner after load/save.
- Core `_RoadNetwork` edge costs now use terrain speed loss
  (`length / speed_factor`) when a DEM is available, so a flatter detour can
  beat a shorter steep route.
- Single-corridor road routing remains unchanged.

## Verification

- Studio test covers crossing-connected and disconnected branches.
- Terrain test checks a flatter detour wins over a shorter steep direct edge.
- 41 targeted tests pass.
- `ruff`, `mypy`, `node --check`, and `pre-commit` pass.

## Limits

- Validation is geometric, not a full road-engineering connectivity model.
- Landing access is warned at 30 m but does not itself block a run.
- Road grade costs require a DEM; without one, routing remains distance-based.

## Closeout

- PR #360 merged to `main` as `4ad83be589167560279ab6b4f4fd83c74c3ae22d`.
- Main CI `41502068526` passed.
- Public demo deployment: `a6be98cc`.
- Live disconnected-road project showed the road warning and run returned HTTP 400.
