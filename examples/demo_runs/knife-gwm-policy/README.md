# Knife Creek GWM sustained policy screen

This is the HMZ-constrained policy built from the 8-entry FVS-BC GWM state
library. It counts both the FVS selection cut and the post-FVS clump harvest,
which v2 under-reported. The omitted clump volume was the reason the earlier
policy entered a zero-yield reserve cycle.

## Construction

- 157 of 160 blocks scheduled; 3 have no treatment option.
- HMZ matrix enforced: M Low/Moderate, L Low, U none.
- 8-entry state library: 216 per-chain states, 192 transitions, 35 canonical
  states, 48 canonical transitions, 2 cycles.
- 1,570 scheduled entries over 300 years.

## Result

- 2,433,385.4 m3 total production
- positive production in all 30 periods
- P00: 208,451.9 m3
- P29: 29,632.1 m3
- annual net after cost under the public envelope: approximately CAD 882k/yr
- NPV 4%: see `finance_envelope.json`

## Status

This is a structural public policy screen, not an approved management plan. The
PSP-derived tree lists, DBH-ranked clump proxy and missing KC CFI remain
explicit caveats.
