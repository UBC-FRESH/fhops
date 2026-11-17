# Knife Creek LiDAR spatial-clump FVS policy

This run uses the 2024 LiDAR canopy inventory directly in a block-level FVS
spatial-clump screen.

## Method

- One-hectare LiDAR sample per block.
- Trees >=20 m grouped into 10 m components and split into 4-10-tree clumps.
- The three largest trees in each 4-10-tree clump are reserved.
- Remaining clump trees are harvested.
- Singletons are reserved.
- Each clump is a separate FVS plot with a stable 3-digit plot key.
- LiDAR TPH is scaled to VRI live stems per hectare.
- Species is assigned Douglas-fir; DBH is LiDAR height-allometry.

## Result

- 134 blocks scheduled / 160 mapped
- 1,230 entries
- 11,458,742 m3 total production
- positive production in all 30 periods
- P00: 393,156 m3
- P29: 290,274 m3
- annual net after cost: ~CAD 4.15M
- NPV 4%: see `finance_envelope.json`

## Limits

This is a structural pilot, not a CFI or an approved plan. The LiDAR DBH is
height-allometry, species is assigned, and the one-hectare sample is scaled to
VRI TPH. It is not a legal-compliance determination.
