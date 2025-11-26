# Medium example (4 machines, 120 blocks, 42 days)

- Landings: 4 (L1, L2, L3, L4), capacities per day: [2, 3, 2, 3]
- Calendar: 42 days of availability for a single four-machine ground-based system.
- Production rates: per-day output when assigned; zeros represent incompatibilities (not present in
  the default bundle).
- Windows: each block has earliest_start and latest_finish within 1..42 (medium-width windows).
- Stand metrics: block volumes follow Lahrsen (2025) daily/cutblock ranges with ≈0.8–2.6 ha areas,
  160–320 m³/ha densities, and stem sizes in the 0.25–0.8 m³ band so med42 behaves like a
  medium-size BC grapple-skidder operation backed by Lahrsen/ADV6N7/Berry/TN-261 productivity
  regressions.

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
