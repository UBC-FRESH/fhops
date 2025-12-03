# FHOPS Large84

- Planning horizon: 84 days
- Blocks: 48 (≈374,704 m³ total volume)
- Large-block share (≥12 ha): 38/48
- Machine roster: feller_buncher=4, grapple_skidder=2, roadside_processor=6, loader=6

Synthetic blocks follow Lahrsen-aligned stand attributes and FHOPS productivity regressions
(Lahrsen harvesters, ADV6N7 grapple skidders with area-derived skidding distance, Berry 2019
processors, TN-261 loaders). Regenerate the dataset with:

```
python scripts/rebuild_reference_datasets.py large84 --seed 20251209
```
