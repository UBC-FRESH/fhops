# Per-landing truck equipment specs

Issue: #357. Branch: `issue-357-truck-specs`.

## Changes

- Core accepts `landing_truck_specs` mapping landing id to `TruckSpec`.
- Per-landing capacity, cycle time, load time, route distance, speed, and
  arrival interval are respected; mill service and bays remain shared from the
  primary/global truck spec.
- CLI adds `--landing-truck-specs` JSON mapping.
- Studio adds a truck-spec panel with payload, cycle, and load-time fields per
  landing.
- Derived cases persist specs; runner writes `landing_truck_specs.json` and
  passes it to the CLI.
- Truck counts still come from `landing_truck_counts` when set, otherwise from
  each spec's count.

## Verification

- Core test uses 1 m³ west and 2 m³ east trucks and asserts per-landing load
  volumes and provenance.
- Studio manifest test asserts spec propagation.
- 36 targeted tests pass; `ruff`, `mypy`, `node --check`, and `pre-commit` pass.

## Limits

- Mill service/bays remain global.
- Truck specs are reference-model equipment parameters, not field calibration.
