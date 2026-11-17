# AFRF decision pack

## Gavin Lake — decision-grade public policy screen

- 2,907 blocks / 5,663.66 ha
- 5,385,148.57 m³ production over 300 years
- 61/61 targets met
- net after harvest cost: approximately CAD 585.6M over 300 years
- annual net after cost: approximately CAD 1.95M/yr
- NPV 4%: approximately CAD 48.3M
- P00: 192 blocks, 175,533 m³, 315-day screen
- P01: 237 blocks, 176,512 m³, 355-day screen

## Knife Creek — HMZ-constrained sustained GWM policy screen

- 160 blocks / 3,481.77 ha; 157 blocks scheduled
- 8-entry FVS-BC state library: 216 per-chain states, 192 transitions, 35 canonical states,
  48 canonical transitions, 2 cycles
- compiled spatial dataset: 140 tracks, 96 treatments
- 1,570 scheduled entries over 300 years
- 2,433,385 m³ total production
- P00: 208,452 m³
- P29: 29,632 m³
- production is positive in all 30 periods
- annual net after cost under the public envelope: approximately CAD 882k/yr
- NPV 4%: approximately CAD 39.3M

The legal HMZ offer matrix is enforced: M Low/Moderate, L Low, U none. The policy now sustains
production because the state library counts the post-FVS clump harvest volume, not only the FVS
selection cut. The earlier v2 library omitted that clump volume and entered a zero-yield reserve
cycle after about 120 years.

A second version applies the 2024 LiDAR reserve scenario as a block-level harvest gate:

- 135 of 160 blocks scheduled
- 1,350 entries
- 2,343,814 m³ total production
- positive production in all 30 periods
- annual net after cost under the public envelope: approximately CAD 850k/yr

This is a real use of LiDAR, but only as a block-level gate. It excludes blocks where the LiDAR
reserve scenario finds no harvest trees. It does not yet replace the DBH-ranked six-tree proxy
inside FVS.

A spatial-clump FVS screen now uses the LiDAR trees directly:

- one-hectare LiDAR sample per block
- 10 m clumps, 4–10 trees, three reserved trees per clump
- block-level FVS entries; LiDAR TPH/BA calibrated to VRI
- tree-level species sampled from VRI composition
- 132 of 160 blocks scheduled
- 624 entries
- 2,564,179 m³ total production
- positive production in all 30 periods
- annual net after cost under the public envelope: approximately CAD 930k
- NPV 4%: approximately CAD 55.6M

This is a structural pilot. LiDAR DBH is height-allometry, tree-level species is sampled from
VRI composition, and the one-hectare sample is scaled to VRI TPH/BA. It is not a CFI or an
approved plan, and it should not be treated as a decision-grade revenue forecast.

The earlier `knife-structural` run remains as a comparison. The `knife-p00-operational` handoff
is from that earlier structural P00, not from this new policy screen.

## Decision

Gavin remains the larger decision-grade public policy screen. Knife now has a legal-HMZ,
sustained GWM policy screen that can be compared with Gavin on volume and finance, with these
caveats:

- Knife tree lists are PSP-derived regional analogs, not KC CFI.
- The LiDAR-constrained plan excludes blocks with no LiDAR harvest trees, but the FVS cut
  still uses the DBH-ranked proxy, not the observed spatial clumps.
- The policy screen is not an approved management plan.

Finance is a public MWP #3 Figure 7 screening envelope, not a budget forecast.

## Early management-plan brief

The Dean's Office draft is `AFRF_EARLY_MANAGEMENT_PLAN.md` (also `.docx` and
`.html`). It separates the working model structure and preview results from the
field-calibration and legal-review work that is still required.
