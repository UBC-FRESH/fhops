# Knife Creek LiDAR spatial-clump FVS policy

This run uses the 2024 LiDAR canopy inventory directly in a block-level FVS
spatial-clump screen.

## Method

- one-hectare LiDAR sample per block
- trees >=20 m grouped into 10 m components and split into 4-10-tree clumps
- three largest trees reserved per clump
- remaining clump trees harvested
- singletons reserved
- each clump is a separate FVS plot with a stable 3-digit plot key
- LiDAR TPH scaled to VRI live stems per hectare
- LiDAR DBH scaled so block BA matches VRI BA
- tree-level species sampled from the VRI species composition

## Result

- 132 blocks scheduled / 160 mapped
- 624 entries
- 2,564,179 m3 total production
- positive production in all 30 periods
- P00: 384,283 m3
- P29: 83,255 m3
- annual net after cost: approximately CAD 930k
- NPV 4%: see `finance_envelope.json`

## Limits

This is a structural pilot, not a CFI or an approved plan. LiDAR DBH is
height-allometry, species is sampled from VRI composition rather than measured
tree-level composition, and the one-hectare sample is scaled to VRI TPH/BA.
Blocks 49, 74 and 108 failed the FVS run and are excluded.
