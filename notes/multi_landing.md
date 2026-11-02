# Studio multi-landing authoring and skidder assignment

Issue: #340. Branch: `issue-340-multi-landing`.

## Scope

- Project `landings` list with primary `landing` retained for compatibility.
- 2D landing panel: add, edit coordinates/label, remove, and promote primary.
- 3D editor: renders all landing pads and can add a landing.
- Derived cases and the Tree Lab runner pass repeated `--landing id,x,y`.
- Core `fhops tree system` accepts `Landing` choices and routes each bunch to
  the lowest-distance viable landing.

## Model

`fhops.ground_system.Landing(landing_id, x_m, y_m)` is a public value object.
`simulate_ground_system(..., landings=...)` tries a terrain route from every
landing to each bunch and assigns the bunch to the shortest route. Unload,
processor, loader, and truck events use the assigned landing coordinates.

The processor and loader are one shared crew servicing the chosen landings.
Per-landing processor/loader fleets and per-landing inventory are not modelled
yet; this is documented in the UI and replay caveats.

## CLI

```bash
fhops tree system scenario.yaml \
  --landing main,1297165.9,837599.4 \
  --landing north,1297177.4,837821.3 \
  ...
```

Landing values may be `id,x,y` or `x,y`.

## Verification

- Core test routes bunches to two landings and checks unload coordinates.
- Studio test checks landing normalization and manifest propagation.
- End-to-end temporary project run:
  - 79 unload events split 52/27 between two landings;
  - processor/loader events appeared at both landing coordinates;
  - replay rendered without page errors.
- 2D landing panel showed both landings and primary promotion controls.

## Limits

- Shared processing/loading crew.
- Global landing inventory rather than per-landing stockpiles.
- Landing assignment is distance-based; grade-adjusted cost can be added later.
