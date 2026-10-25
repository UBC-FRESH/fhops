# Multi-day marine barge cycles

Date: 2026-10-25
Status: design; no solver change yet.
Parent issue: #197
Task: #196 (P13.1)

## Problem

FHOPS Phase I assumes a barge leaves, sails, unloads, and returns within one
planning day. The current fleet constraint is:

```text
mt[route, day] * barge_cycle_minutes
  <= barges_on_contract * regular_minutes
```

`mt` is the integer number of barge trips on a route/day, and
`regular_minutes` defaults to 510. A real coastal voyage can exceed that by a
wide margin.

Regression case:

- Quatsino Sound -> Ladysmith Harbour.
- Loaded leg: 1,910 minutes.
- Empty return: 1,910 minutes.
- Load/unload and terminal handling: 135 minutes.
- Barge cycle: 3,955 minutes.
- One barge, 10,000 m3, eight-day horizon.

The current model returns `infeasible`. Adding eight barges would make the
constraint numerically pass but would fake the fleet. The regression fixture is
at `examples/hauling_marine_multiday/`.

## Candidate formulations

### Option A — horizon barge-day budget only

Change the fleet constraint to:

```text
sum(route, day) mt[route, day] * barge_cycle_minutes
  <= barges * regular_minutes * horizon_days
```

Advantages:

- small change;
- allows a long trip to consume a multi-day budget;
- enough for a fleet-level capacity check.

Problems:

- `mt[route, day]` still behaves as if the trip happens on one day;
- the water volume can be delivered before the barge would actually arrive;
- port inventory and demand timing are wrong;
- a trip can start too late to finish within the horizon.

Rejected as the main model. It may be a useful lower-bound check, not the
physical model.

### Option B — explicit departure and arrival days with in-transit inventory

Add an explicit voyage duration and separate departure/arrival flow:

- `voyage_days = ceil(barge_cycle_minutes / regular_minutes)` (8 in the
  regression), or a validated override on `MarineRoute`;
- `mww` remains the departure/water-out flow on the departure day;
- add `mwa` (water arrival) for the destination, with:

```text
mwa[route, sort, day] = mww[route, sort, day - voyage_days]
```

- add an in-transit inventory state or carry the barge volume until arrival;
- the destination port inventory receives `mwa`, not `mww`;
- enforce barge occupancy with a sliding window:

```text
sum_{t' = day - voyage_days + 1}^{day}
  sum_route mt[route, t'] <= barges
```

per contractor/barge type and day;

- disallow or explicitly account for trips that would arrive after the
  horizon;
- keep `voyage_days = 1` as the backward-compatible path for the existing
  Sunshine Coast -> Howe Sound fixture.

Advantages:

- preserves daily port inventory and demand timing;
- represents one barge on a multi-day voyage without dummy barges;
- supports multiple trips and multiple barges;
- keeps the existing day-trip model unchanged.

Costs:

- new variables for arrival/in-transit volume;
- more complex port inventory and reporting;
- initial barge state (a voyage already underway) needs a decision;
- a non-integer day duration needs a documented rounding rule.

This is the recommended formulation.

### Option C — continuous-time barge schedule as the Phase I authority

Move the voyage timing into the Phase II/III barge scheduler and have Phase I
consume a barge availability calendar.

Advantages:

- most physically precise;
- reuses the existing barge-cycle scheduler.

Problems:

- couples the daily flow MIP to the detailed scheduler;
- larger change than needed for the transport cost;
- Phase II/III already reports synchronized road windows but does not
  hard-link the two schedules.

Defer. Option B is the right first step; Option C can replace the timing layer
later if the scheduler becomes the authority.

## Recommended model

Use Option B.

### Contract and problem data

- Derive `voyage_days` from `ceil(barge_cycle_minutes / regular_minutes)`.
- Add a validated optional `voyage_days` override on `MarineRoute` only if a
  route needs a different operational duration than the cost cycle. Decide in
  P13.2; do not add it just for the fixture.
- Add `voyage_days`, `departure_day`, and `arrival_day` to `MarineLane`
  reporting.
- Add a `marine_transit` initial-inventory field only if P13.2 supports
  voyages already underway at the horizon start.

### Flow and capacity

- `mww` is departure volume.
- `mwa` is arrival volume.
- `mwa[route, sort, day] = mww[route, sort, day - voyage_days]`.
- Destination port inbound uses `mwa`; origin port outbound uses `mww`.
- Barge capacity upper/lower bounds stay linked to `mt` on the departure day.
- Barge fleet occupancy uses the sliding window above.
- Trips that cannot arrive by the horizon are disallowed in the base case,
  or explicitly reported as in-transit with a carry-out value. Do not silently
  drop them.

### Demand timing

- Demand before arrival is infeasible unless initial destination inventory
  covers it.
- The regression fixture has demand on day 8, matching a day-1 departure.
- Add a future test for a late departure that misses the horizon.

### Costs and reporting

- Barge variable and terminal handling remain per trip.
- Fixed barge/truck dispatch remains a Phase II/contract concern; do not
  silently add it to Phase I.
- `barge_trips` reports departure and arrival days.
- `marine_flows` reports departure/arrival split.
- A new transit inventory table is preferable to hiding the voyage in port
  inventory.

### Backward compatibility

- `voyage_days = 1` must reproduce the existing Sunshine Coast -> Howe Sound
  fixture and all current tests.
- No new required YAML fields for day-trip routes.
- Existing cost and flow artefacts keep their columns; new columns are
  additive.

## Regression fixture

`examples/hauling_marine_multiday/` is a synthetic, redistributable case:

- one block, one yard, one barge, 20 trucks;
- 10,000 m3 barge capacity;
- 3,955-minute cycle;
- eight-day horizon;
- demand on day 8;
- no truck-capacity or demand mismatch.

`tests/hauling/test_marine_multiday.py` uses a strict xfail assertion that the
case is optimal. It fails now on the barge fleet constraint and will become
XPASS when the model supports multi-day voyages. That XPASS is the signal to
remove the xfail and add the full arrival-timing assertions.

## Implementation split

P13.2 (recommended next task):

1. add voyage-days and arrival/transit variables;
2. update destination port inventory and barge occupancy;
3. update reporting with departure/arrival days;
4. flip the xfail into positive assertions;
5. add late-departure and multiple-barge cases;
6. update docs and formulation notes.

P13.3: validation, CLI/reporting, and close-out.

## Open questions

- Should a trip already in transit at day 1 be allowed through an initial
  barge state, or rejected in the first release?
- Should `voyage_days` be derived only, or configurable per route?
- How should a non-integer cycle be rounded for capacity: ceil days
  (conservative) or continuous barge-minutes with day-level port flows?
- Should trips that would arrive after the horizon be disallowed or carried out
  with an explicit penalty?

## Decision

Adopt Option B for P13.2. Do not use a horizon-only budget as the physical
model, and do not add dummy barges. Keep the existing day-trip behavior and
fixture as the regression baseline.
