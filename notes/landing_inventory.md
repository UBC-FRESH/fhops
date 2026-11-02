# Per-landing inventory and grade-aware landing choice

Issue: #343. Branch: `issue-343-landing-inventory`.

## Changes

- Landing choice now uses `landing_route_cost(route) = distance / speed_factor`
  instead of raw distance. A longer flatter route can beat a shorter steep one.
- Landing inventory and capacity are tracked per landing using the load’s
  assigned landing.
- Truck dispatch draws from the selected landing’s stockpile; capacity overflow
  dispatches from that landing only.
- `GroundSystemResult.landing_inventory` and the serialized manifest expose
  per-landing `final_m3`, `max_m3`, and `capacity_m3`.
- Replay HUD shows per-landing final/peak stockpiles.

## Verification

- `test_landing_route_cost_prefers_faster_route`.
- `test_ground_system_routes_bunches_to_multiple_landings` now includes trucks
  and per-landing capacity; it asserts both landing keys, capacity metadata, and
  bounded peaks.
- Existing single-landing inventory tests remain green.
- 32 targeted tests pass.

## Limits

- Landing inventory is per landing, but processor/loader are still one shared
  crew.
- Capacity is a common per-landing value; per-landing capacities can be split
  out later.
- Grade affects route speed and landing choice; a separate landing-construction
  cost model is out of scope.

## Closeout

- PR #344 merged to `main` as `104eb8f51cf7ec8a5ac08daa374f2d13efbf936a`.
- Main CI `41411242696` passed.
- Public demo deployment: `15679a01`.
- Live two-landing run reported separate stockpiles (`north 24.9/37.1 m³`,
  `south 11.1/47.4 m³`) and replay rendered the inventory text.
