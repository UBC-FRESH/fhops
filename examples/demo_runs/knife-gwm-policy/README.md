# Knife Creek GWM multi-entry policy screen

This run replaces the earlier structural single-cycle exposure with a policy built from the
4-entry FVS-BC GWM state library. It is a public policy screen, not an approved management plan.

## Policy construction

- 157 of 160 blocks scheduled; 3 blocks have no treatment option.
- Each block follows the highest-cut allowed canonical transition path.
- GWM entries repeat on a 30-year cycle, staggered across 30 phases.
- 1,306 scheduled entries over 300 years.
- State library: `ws4/state_library_v2` (120 states, 96 transitions, 32 canonical states).
- Dataset: `ws4/dataset_kc_spatial_v4` (128 tracks, 79 treatments).

## Result

- 574,458.2 m³ total production
- 172,832.0 m³ in P00
- production declines to zero after P11
- public-envelope annual net after cost: approximately CAD 208k/yr
- NPV 4%: see `finance_envelope.json`

The canonical graph has four cycles, but the policy enters a reserve cycle after about 120 years.
This is a real model result: the current PSP-derived library does not support a sustained-yield
GWM harvest beyond that point. It does not replace the Gavin Lake decision-grade policy screen.
