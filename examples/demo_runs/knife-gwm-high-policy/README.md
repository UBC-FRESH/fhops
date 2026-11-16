# Knife Creek GWM high-regime upper-bound policy screen

This run is the sustained-yield upper bound for the current four-entry FVS-BC GWM
state library. It deliberately offers High, Moderate and Low in every HMZ group.

## Why this exists

The HMZ-constrained `knife-gwm-policy` enters a reserve cycle after about 120
years and stops producing. The high-regime graph contains positive self-loop
cycles, so it sustains production through 300 years. That makes it useful as a
model upper bound and a policy diagnostic. It is **not** an HMZ-compliant or
approved management plan.

## Result

- 160 blocks / 3,481.77 ha; 157 scheduled
- 1,570 entries
- 1,329,309.2 m3 total production
- production continues through P29
- P00: 75,730.8 m3
- public-envelope annual net after cost: approximately CAD 482k/yr
- NPV 4%: see `finance_envelope.json`

The HMZ-constrained run remains in
`examples/demo_runs/knife-gwm-policy`.
