# FHOPS Small21

- Planning horizon: 21 days
- Blocks: 6 (≈15,967 m³ total volume)
- Large-block share (≥12 ha): 3/6
- Machine roster: feller_buncher=2, grapple_skidder=1, roadside_processor=3, loader=3

Synthetic blocks follow Lahrsen-aligned stand attributes and FHOPS productivity regressions
(Lahrsen harvesters, ADV6N7 grapple skidders with area-derived skidding distance, Berry 2019
processors, TN-261 loaders). Regenerate the dataset with:

```
python scripts/rebuild_reference_datasets.py small21 --seed 20251209
```
