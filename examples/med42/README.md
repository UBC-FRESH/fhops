# Medium example (4 machines, 29 blocks, 42 days)

- Landings: 4 (L1, L2, L3, L4) with daily capacities [2, 3, 2, 3].
- Calendar: 42 days of availability for a single four-machine ground-based system (feller-buncher,
  grapple skidder, roadside processor, loader).
- Blocks: 29 total with ≈60 % of the volume carried by 20 ha-class blocks (10–18 ha, ≈320–360 m³/ha)
  and the remainder made up of 1.3–2.3 ha satellites (≈140–190 m³/ha). Total workload is
  ≈22.5 k m³, yielding ~46 bottleneck days on the processor vs. the 42-day planning horizon so
  heuristics must prioritise which blocks finish.
- Stand metrics: sampled from Lahrsen (2025) daily/cutblock ranges; the large blocks track the
  Lahrsen averages for BC grapple-skidder systems while the satellites stay within the small-block
  FPDat envelope.
- Production rates: computed from the FHOPS productivity helpers
  (Lahrsen 2025 feller-buncher, ADV6N7 grapple skidder, Berry 2019 processor, TN-261 loader) and
  scaled to the 24 h/3-shift day.
- Windows: each block’s earliest_start/latest_finish lies inside 1..42 with medium-width windows so
  the solver has limited slack but no degenerately wide blocks.

Quick start:
  fhops validate examples/med42/scenario.yaml
  fhops solve-mip examples/med42/scenario.yaml --out examples/med42/out/mip_solution.csv
  fhops solve-heur examples/med42/scenario.yaml --out examples/med42/out/sa_solution.csv --iters 8000 --seed 1
  fhops evaluate examples/med42/scenario.yaml examples/med42/out/mip_solution.csv

Harvest systems:
- Blocks ship without a ``harvest_system_id`` column so you can experiment with multiple chains. When you
  need deterministic assignments, add the column to ``data/blocks.csv`` using IDs from
  ``docs/reference/harvest_systems.rst`` (e.g., ``ground_fb_skid`` for grapple-skidder workflows or
  ``cable_running`` for skyline blocks).

Regeneration:
- Run ``python scripts/rebuild_med42_dataset.py`` to regenerate ``data/blocks.csv`` and
  ``data/prod_rates.csv``. Adjust ``--min-blocks``, ``--target-bottleneck-days``, or
  ``--max-large-blocks`` to explore different workload/capacity mixes while keeping Lahrsen-aligned
  stand metrics.
