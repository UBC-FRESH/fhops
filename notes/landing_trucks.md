# Per-landing truck fleets

Issue: #349. Branch: `issue-349-landing-trucks`.

## Changes

- `simulate_ground_system(..., landing_truck_counts={landing_id: count})` assigns
  independent deterministic truck availability lists per landing.
- CLI adds repeatable `--landing-truck landing_id:count`.
- When no per-landing counts are supplied, the existing shared global truck
  fleet is retained for backward compatibility.
- Truck IDs include the landing (`T-west-01`); the mill/service model remains
  shared.
- Studio landing rows have a truck-count field; blank means shared fleet, and
  any assignment writes counts for every landing.
- Run provenance records the landing truck counts.

## Verification

- Core test asserts `T-west-01`/`T-east-01`, separate per-landing dispatch, and
  provenance.
- Studio manifest test asserts `landing_truck_counts` propagation.
- 35 targeted tests pass.

## Limits

- Truck capacity/cycle/mill settings remain global; per-landing equipment specs
  are a future extension.
- A landing with zero trucks raises a clear error if its stockpile needs
  dispatch.

## Closeout

- PR #349 merged to `main` as `4580115946b7c594c8c28a6e382244f871f2f098`.
- Main CI `41422164978` passed.
- Public demo deployment: `22094577`.
- Live Studio smoke test showed the landing truck input with no page errors.
