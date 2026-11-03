# Studio system presets

Issue: #393. Branch: `issue-393-system-presets`.

## Change

Studio’s Machines panel now has a system preset selector:

- **Full-tree system**: feller-buncher + grapple skidders + roadside processors + loaders;
- **CTL harvester + forwarder**: harvester + forwarders + loaders.

Applying a preset:

- keeps terrain, retention, roads, landings, trucks, economics, and comments unchanged;
- rebuilds machine roles and landing assignments;
- adds/removes processor machines;
- ensures a second loader (`H4-B`) when a second landing exists;
- applies the CTL forwarder reference profile:
  - 16 m³ payload,
  - 1.2/1.0 m/s empty/loaded,
  - Eriksson distance-varying model,
  - 300 s load / 180 s unload,
  - 0.3 m³ mean stem;
- clears forwarder-specific specs when switching back to full-tree.

Preset application is undoable and only takes effect in a run after Save.

## Verification

- Browser smoke test applied full-tree then CTL on the live CTL project:
  - H1 changed to feller-buncher then harvester,
  - H2/H3 changed to grapple skidder then forwarder,
  - processors appeared/disappeared,
  - H4/H4-B loaders retained,
  - no page errors.
- Existing Studio tests and pre-commit pass.
