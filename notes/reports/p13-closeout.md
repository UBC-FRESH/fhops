# P13 close-out — Multi-day marine barge cycles

Date: 2026-10-25
Parent issue: #197
Design: `notes/multiday_marine_cycles.md`
Evidence commits: `65b0d2b1` (P13.1 design/fixture), `afa52c8` (P13.2 implementation merge)
Pull request: #200

## Outcome

P13 adopts Option B: explicit departure and arrival timing with in-transit volume and a
sliding-window barge occupancy check. One barge can now cover a voyage longer than a day without
adding dummy barges or relaxing capacity checks.

P13.1 recorded the current one-day limitation, compared the horizon-budget and continuous-time
alternatives, added the redistributable Quatsino Sound → Ladysmith fixture, and left a strict xfail
that reproduced the infeasibility for the right reason. P13.2 implemented the model, flipped that
xfail into positive assertions, and added late-departure and multiple-barge coverage.

## Model and artefacts

- `MarineLane` carries `arrival_lag_days` and `occupancy_days`, derived from the validated lane:
  `arrival_lag_days = ceil(loaded transit + unload + destination handling / regular minutes)` and
  `occupancy_days = ceil(full barge cycle / regular minutes)`.
- Departure water volume remains on the departure day. Arrival/delivery volume is linked to the
  same departure key and enters destination port inventory, truck drayage, and demand on the arrival
  day.
- The barge fleet check is a sliding window: every departure whose occupancy window covers the day
  counts against the contractor/barge-type fleet. Departures that cannot complete inside the
  horizon are forced to zero.
- `marine_flows` adds `arrival_day`/`arrival_scenario_day`; `barge_trips` adds arrival, transit, and
  occupancy days. The hauling output schema is bumped additively to `1.1.0`.
- Day-trip lanes keep `arrival_lag_days = 0` and `occupancy_days = 1`; the Sunshine Coast → Howe
  Sound fixture and its tests are unchanged.

## Regression evidence

Quatsino Sound → Ladysmith, 10,000 m³, one barge:

- status **optimal**;
- cost **62,771.667 CAD**;
- departure day 1;
- cargo arrival day 5;
- barge occupancy 8 days;
- demand day 8;
- one barge trip.

Demand before arrival is infeasible. A 20,000 m³ case with two barges covers two trips. The
full suite, including all existing day-trip marine tests, passes.

## Verification

```bash
ruff format src tests
ruff check src tests
mypy src
pytest
pre-commit run --all-files
PATH=/tmp/opencode/pandoc-3.1.3/bin:$PATH sphinx-build -b html docs /tmp/opencode/fhops-p13-docs -W
```

CI run `40237995538` passed for PR #200 (lint, mypy, pytest, pre-commit, notebooks, and docs).
`fhops haul validate` and `fhops haul plan` on the multiday fixture produce the optimal result and
all expected artefacts.

## Limits

- Delivery occurs on the cargo-arrival day; later port storage within the voyage is not modeled.
- Voyages already in transit at the horizon start are not modeled.
- A departure that would finish after the horizon is disallowed rather than carried out with a
  terminal value.
- No current carrier/terminal quotes, tide/weather routing, or Phase II/III scheduler rewrite.
- The design note's single `voyage_days` concept is implemented as two explicit values (arrival lag
  and occupancy) so cargo timing and barge availability can differ correctly.

## Follow-ups

- Initial in-transit barge state at the horizon start.
- Explicit end-of-horizon valuation for late departures if a planning workflow needs carry-out.
- Port storage after arrival when a later demand window is modeled.
- Optional continuous-time barge scheduling if Phase II/III becomes the timing authority.

## Phase status

P13 is complete. P14 (Consume FEMIC-compiled LidarBC products) is the next queued phase.
