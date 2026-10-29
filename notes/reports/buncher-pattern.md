# Feller-buncher tree-order pattern

Date: 2026-10-29

## Decision

`fhops tree simulate` and `simulate_block` accept:

- `auto` (default): `strip` for a `feller_buncher`, `nearest` for other roles
- `nearest`: original nearest-feasible tree policy
- `strip`: serpentine rows, with candidate strip widths and both axes scored by
  the full travel path
- `tsp`: nearest-neighbour tour with bounded deterministic 2-opt

The manifest records the selected pattern.  Processing time is unchanged; only
tree order and travel change.

## Synthetic fixture check

Start at `(881700, 627500)`, reach 10 m, 12 trees:

| Pattern | Processed | Travel (m) | Simulated time (s) |
|---|---:|---:|---:|
| nearest | 12 | 217.29 | 1,092.00 |
| strip | 12 | 217.36 | 1,092.14 |
| tsp | 12 | 226.99 | 1,111.40 |

The strip order is systematic and essentially tied with nearest on this tiny
fixture; it is not claimed to be shorter in every case.  The TSP order in this
run is longer in simulated movement because the reach radius absorbs many short
nearest moves.  These are execution heuristics, not field-calibrated felling
patterns.

## Why this is better than a blind roomba

The old policy always jumped to the nearest individual tree.  `strip` works
contiguous rows and turns around at row ends, which is the pattern a
feller-buncher can actually execute.  `tsp` is available when the goal is a
short tour rather than a strip layout.  Neither pattern changes the tree
inventory or the block/day planning authority.
