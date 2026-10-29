# Ground-based system simulation notes

Status: merged to `main` via PR #278. The CLI exposes feller/skidder/loader rate controls, processor model selection, shifts, trucks, terrain, and deterministic/stochastic downtime.

The module `fhops.ground_system` adds a deterministic multi-machine event layer
for one block:

1. feller-buncher events come from the existing single-machine spatial model;
2. processed trees are grouped into bunches;
3. skidders are greedily dispatched to the earliest available bunch and return
   to the landing;
4. one or more optional roadside processors handle skidder loads before the loader;
5. one loader processes loads in arrival order;
6. optional absolute downtime windows or seeded stochastic breakdowns can delay tasks.

The first implementation uses flat terrain, one landing, configurable default
cycle times, and no shift calendar or trucking. It is not field-calibrated and
does not validate the stem model.

The two research-forest demos in `build/tree_scale_data/` are scratch data:
real FEMIC mature stand footprints plus synthetic plot-conditioned inventories.
They are not committed fixtures and must not be presented as surveyed stands.

Next steps after review:

- replace default skidder/loader times with calibrated regressions;
- add full road-network and landing-search routing (optional DEM/single-corridor access is now present);
- add loader-blocking truck dispatch and breakdowns (shift windows and downstream truck tracking are now present);
- decide whether to ship the external Three.js viewer as an example or keep it
  outside core.

## Sensitivity check

`notes/reports/tree_system_sensitivity.md` records the 2026-10-29 bounded grid.
The processor rate dominates the demo makespan; truck count has little effect
because trucking is still a downstream tracker. Shift length is first-order.
The demo data remain synthetic scratch inputs.
