# Ground-based system simulation notes

Status: merged to `main` via PR #278. The CLI exposes feller/skidder/loader rate controls.

The module `fhops.ground_system` adds a deterministic multi-machine event layer
for one block:

1. feller-buncher events come from the existing single-machine spatial model;
2. processed trees are grouped into bunches;
3. skidders are greedily dispatched to the earliest available bunch and return
   to the landing;
4. one loader processes loads in arrival order.

The first implementation uses flat terrain, one landing, configurable default
cycle times, and no shift calendar or trucking. It is not field-calibrated and
does not validate the stem model.

The two research-forest demos in `build/tree_scale_data/` are scratch data:
real FEMIC mature stand footprints plus synthetic plot-conditioned inventories.
They are not committed fixtures and must not be presented as surveyed stands.

Next steps after review:

- replace default skidder/loader times with calibrated regressions;
- add DEM road/landing routing;
- add shift/day state and breakdowns;
- decide whether to ship the external Three.js viewer as an example or keep it
  outside core.
