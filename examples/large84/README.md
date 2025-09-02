# Large example (16 machines, 50 blocks, 84 days, 8 landings)

- Landings: 8 (L1, L2, L3, L4, L5, L6, L7, L8), capacities per day: [2, 3, 3, 4, 4, 3, 4, 4]
- Calendar: weekends off + 3 random down days per machine.
- Production rates: per-day output when assigned; ~25% incompatibilities (rate=0).
- Windows: each block has earliest_start and latest_finish within 1..84.

Quick start:
  fhops validate examples/large84/scenario.yaml
  fhops solve-mip examples/large84/scenario.yaml --out examples/large84/out/mip_solution.csv
  fhops solve-heur examples/large84/scenario.yaml --out examples/large84/out/sa_solution.csv --iters 20000 --seed 1
  fhops evaluate examples/large84/scenario.yaml examples/large84/out/mip_solution.csv
