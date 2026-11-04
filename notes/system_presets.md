# Studio system presets

Issue: #393; custom-fleet follow-up #407. Branch: `issue-407-preset-compare`.

## Change

Studio’s Machines panel now has a system preset selector:

- **Full-tree system**: feller-buncher + grapple skidders + roadside processors + loaders;
- **CTL harvester + forwarder**: harvester + forwarders + loaders.

Applying a preset:

- keeps terrain, retention, roads, landings, trucks, economics, and comments unchanged;
- rebuilds machine roles and landing assignments;
- adds/removes processor machines;
- ensures one loader and one processor per landing;
- applies the CTL forwarder reference profile:
  - 16 m³ payload,
  - 1.2/1.0 m/s empty/loaded,
  - Eriksson distance-varying model,
  - 300 s load / 180 s unload,
  - 0.3 m³ mean stem;
- clears forwarder-specific specs when switching back to full-tree.

Preset application is undoable and only takes effect in a run after Save.

## Custom fleets

Presets no longer assume the standard `H1`–`H5-B` identifiers:

- existing machines are matched by role, so custom IDs are preserved;
- added machines get a unique ID derived from the preferred base
  (`H5-2`, `H4-B-2`, …) when the base is already in use;
- custom extraction fleets keep their machine count;
- every landing receives a loader and, for the full-tree preset, a processor;
- extra fleet machines are assigned to landings round-robin.

## Verification

- Browser smoke test applied full-tree then CTL on the live CTL project:
  - H1 changed to feller-buncher then harvester,
  - H2/H3 changed to grapple skidder then forwarder,
  - processors appeared/disappeared,
  - H4/H4-B loaders retained,
  - no page errors.
- Custom-ID browser smoke used `F1`, `X2`, `H5`, `H4-B`, and `H1` with two
  landings. Full-tree produced `F1` feller-buncher, the three extraction
  machines as grapple skidders, `H5-2`/`H5-B` processors (one per landing), and
  `H1`/`H4-B-2` loaders (one per landing), with no duplicate IDs. CTL removed
  the processors and retained both loaders.
- Existing Studio tests and pre-commit pass.
