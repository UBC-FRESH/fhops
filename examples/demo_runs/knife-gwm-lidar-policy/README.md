# Knife Creek LiDAR-constrained GWM policy

This run applies the existing sustained HMZ-constrained policy only to blocks where
the 2024 LiDAR reserve scenario identifies harvest trees.

- 160 blocks on the map
- 135 blocks scheduled
- 1,350 entries
- 2,343,814 m3 total production
- positive production in all 30 periods
- public-envelope annual net after cost: approximately CAD 849k/yr
- NPV 4%: see `finance_envelope.json`

The LiDAR gate is block-level: blocks with zero harvest trees are excluded. It is not yet
a replacement of the DBH-ranked six-tree proxy inside FVS. LiDAR DBH is height-allometry,
and the inventory has no species or understory.
