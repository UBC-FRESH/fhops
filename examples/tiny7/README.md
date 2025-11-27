# FHOPS Tiny7

- Planning horizon: 7 days
- Blocks: 9 (≈11,990 m³ total volume)
- Large-block share (≥12 ha): 0/9
- Machine roster: feller_buncher=1, grapple_skidder=1, roadside_processor=1, loader=1

Synthetic blocks follow Lahrsen-aligned stand attributes and FHOPS productivity regressions
(Lahrsen harvesters, ADV6N7 grapple skidders with area-derived skidding distance, Berry 2019
processors, TN-261 loaders). Regenerate the dataset with:

```
python scripts/rebuild_reference_datasets.py tiny7 --seed 20251209
```
