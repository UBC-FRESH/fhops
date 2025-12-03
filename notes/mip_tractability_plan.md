# Operational MILP Tractability Plan

## Context

- Med42 and larger datasets now sit much closer to full-horizon capacity after the recent work_scale increases (small ≈17/21 days, med ≈38/42, large ≈84/84 for heuristic makespans).
- Gurobi solves small21 to optimality (~5 seconds) but med42 stalls for many hours at default settings, even with 36 threads.
- Anecdotally, loosening the gap (e.g., `--gap 0.05`) should reduce runtime, but we don’t yet have confirmed measurements for med42—collecting that data is part of this plan.
- Goal: ensure `fhops solve-mip-operational` (and benchmarks) return a feasible plan with a controllable gap in a predictable amount of time (≤ 1 hour) for med42/large84.

## Plan

### [x] 1. Capture baseline solver diagnostics
- [x] 1.1 Run med42 with `--debug --solver-option LogFile=med42_default.log --solver-option Threads=<current> --solver-option TimeLimit=600` (gap unset) to gather a Gurobi log (root presolve stats, early nodes). Stop once enough log info is captured if it hasn’t terminated. *(Completed: med42_default.log shows presolve cuts it to 55 k×56 k, incumbent rises to 37.4 k with 2.1 % gap after ~590 s.)*
- [x] 1.2 Extract model statistics (variables, constraints, binaries) for tiny/small/med/large via the build step (`--debug`) to quantify the jump in size. *(Done 2025-12-02 via `fhops solve-mip-operational … --debug --solver-option TimeLimit=<short>` with Gurobi: see table below.)*
- [x] 1.3 Identify whether Gurobi ever finds an incumbent on med42 at default settings and how quickly, using log timestamps (check med42_default.log for heuristics vs B&B timing). *(The 120 s run hits the first positive incumbent at ~10 s (≈7 k objective) and climbs to 36.2 k by 93 s, but the best bound stays at 38.2 k so ~5.4 % gap remains when the time limit fires. Appending these timings to the notes below for future tuning.)*

| Scenario | Rows | Cols | Nonzeros | Integer / binary vars | Presolve result | 120 s status (Threads=36) |
| --- | --- | --- | --- | --- | --- | --- |
| tiny7 | 1 119 | 666 | 2 780 | 370 / 356 | 248×242, solved at root | Optimal in 0.05 s |
| small21 | 23 247 | 10 476 | 56 766 | 7 866 / 7 740 | 6 984×7 260 | Time limit at 60 s with 0.17 % gap |
| med42 | 174 078 | 68 940 | 417 444 | 58 680 / 58 176 | 55 251×56 784 | Time limit at 120 s with 5.37 % gap (best incumbent 36 247) |
| large84 | 10 477 608 | 3 640 128 | 24 663 936 | 3 522 816 / 3 518 784 | Presolve only trims 151 938 rows + 65 376 cols before hitting time limit | No nodes explored within 120 s; only heuristic incumbent (−374 703) |

Key observations:
- Problem size explodes roughly ×150 (rows) and ×340 (columns) between small21 and large84, which explains why the current Pyomo-to-Gurobi bridge barely finishes presolve on large84 before the 120 s limit triggers. Any tractable workflow for large84 will need either a decomposed model or aggressive presolve/time budgets.
- Med42’s incumbent behaviour is “fast but shallow”: the root heuristics deliver a decent solution (~7 k) within 10 s and continue improving to 36 k without exploring any B&B nodes, yet the LP bound moves slowly. Further runtime is spent squeezing gap via cutting planes rather than branching. This reinforces the need for better warm starts (Plan §2) and explicit time/gap budgets (Plan §3) so users can stop once the incumbent plateaus.
- Large84 currently runs with a single active thread during presolve despite `Threads=36`. Gurobi drops to one thread when the LP formulation is too large for multi-threaded presolve, so splitting the problem or switching formulations may be mandatory if we want meaningful progress before the time limit.

### [ ] 2. Heuristic warm starts (prereq for sweeps)
- [x] 2.1 Add support for feeding heuristic assignments as a MIP start (e.g., `--incumbent assignments.csv`) by mapping the CSV produced by `fhops solve-heur ... --out` onto Pyomo `x`/`prod` before invoking Gurobi. *(Done via `solve_operational_milp(..., incumbent_assignments=...)`; CLI exposes `--incumbent`, and docs/tests confirm the workflow.)*
- [ ] 2.2 Run back-to-back med42 solves (no start vs greedy start vs 60 s SA start) with identical solver budgets to quantify incumbent quality, gap trajectory, and runtime impact.
- [ ] 2.3 Document the warm-start behaviour (limitations, required CSV schema) in the notes/CLI docs so sweeps can assume access to a seeded incumbent.

Med42 warm-start experiment (2025-12-03):

| Start source | Prep command | Gurobi behaviour (`TimeLimit=120`, `Threads=36`) | Best objective | Gap | Notes |
| --- | --- | --- | --- | --- | --- |
| none | – | Matches baseline log: heuristics find incumbent 36 247 at ~97 s, best bound 38 193 → gap 5.37 %. No assignment written because Pyomo marks solve as `aborted` | 36 247 | 5.37 % | Reference log `tmp/mip_logs/med42_no_start.log` |
| greedy seed (`iters=0`) | `fhops solve-heur examples/med42/scenario.yaml --iters 0 --out tmp/med42_greedy_incumbent.csv` (~2 s) | Gurobi emits `Warning: Completing partial solution with 54144 unfixed non-continuous variables out of 58680` followed by `User MIP start did not produce a new incumbent solution`; progress identical to baseline | 36 247 | 5.37 % | We only seed `x`/`prod`, so the start is incomplete (transition binaries, activation flags, landing inventories stay free) |
| SA seed (`iters=2000`, runtime ≈106 s) | `/usr/bin/env time -f 'SA runtime %E' fhops solve-heur ... --iters 2000 --out tmp/med42_sa_incumbent.csv` | Same warning as the greedy run; Gurobi discards the start and reproduces the baseline curve (best 36 247, gap 5.37 %) | 36 247 | 5.37 % | Seeding higher-quality assignments has no effect until we populate the auxiliary binaries and inventory vars |

Takeaway: simply loading the heuristic assignment matrix (machine/block/day/shift + optional production) is not enough—Gurobi insists on values for the remaining 54 k integer vars, so the warm start never becomes an incumbent. Next step for §2.2/2.3 is to extend `_apply_incumbent_start` (or a follow-up helper) to derive the missing variables (transition `y`, activation binaries, landing inventories, mobilisation states) from the incumbent schedule before re-running the comparison.

### [ ] 3. Budgeted option sweep
- [ ] 3.1 Run med42 with staged options (`TimeLimit`, `MIPGap`, `Threads`, `Presolve`, `Heuristics`, with/without warm starts) and log objective/gap/runtime for each combination to map the time-vs-gap curve.
- [ ] 3.2 Repeat for small21 and large84 (short time limits) to understand scaling and choose sensible defaults per tier.
- [ ] 3.3 Document the “inflection point” (e.g., gap ≤5 % in ≤20 min) and recommend default CLI settings (`--gap 0.05`, `--solver-option TimeLimit=1800`, etc.).

### [ ] 4. Model tuning / decomposition
- [ ] 4.1 Investigate whether certain constraint families (landing inventory, mobilisation) make the LP relaxation weak; consider strengthening cuts or relaxing non-critical constraints.
- [ ] 4.2 Explore tactical relaxations (e.g., solving at day resolution, then refining) if exact day×shift models remain too slow for large84.

### [ ] 5. CLI workflow improvements
- [ ] 5.1 Expose executor-friendly defaults: add CLI presets (e.g., `--budget short|long`) that set `gap`, `time_limit`, and solver options automatically.
- [ ] 5.2 Surface progress telemetry (gap over time) via watch mode so long-running solves report diminishing returns.

### [ ] 6. Automation & regression coverage
- [ ] 6.1 Integrate the option sweep into CI (daily/weekly) to detect regressions in tractability as scenarios evolve.
- [ ] 6.2 Update documentation (README, CLI help) to describe recommended solver budgets per scenario tier.


## GEP Notes

This ran in "a few minutes" (did not time it, but it was not very long):

```bash
(.venv) gep@jupyterhub01:~/projects/fhops$ fhops solve-mip-operational examples/med42/scenario.yaml --out tmp/med42_mip.csv --solver gurobi --solver-option Threads=18 --solver-option MIPGap=0.05 
Operational MILP solver_status=ok termination=optimal objective=36380.70123400002
Assignments written to tmp/med42_mip.csv
KPI Summary
Production
  total_production: 38029.035
  staged_production: 164.194
  remaining_work_total: 164.194
  completed_blocks: 11.000
  makespan_day: 42
  makespan_shift: S1
Mobilisation
  mobilisation_cost: 7014.560
  mobilisation_cost_by_machine: H1=1021.88, H2=645.12, H3=1134.12, H4=811.32, H5=809.88, H6=648.0, H7=594.76, H8=646.56, H9=702.92
  mobilisation_cost_by_landing: L1=1779.96, L2=1993.4, L3=1247.32, L4=1993.88
Utilisation
  utilisation_ratio_mean_shift: 1.000
  utilisation_ratio_weighted_shift: 1.000
  utilisation_ratio_mean_day: 0.627
  utilisation_ratio_weighted_day: 0.627
  utilisation_ratio_by_machine: H1=1.0, H2=1.0, H3=1.0, H4=1.0, H5=1.0, H6=1.0, H7=1.0, H8=1.0, H9=1.0
  utilisation_ratio_by_role: feller_buncher=1.0, grapple_skidder=1.0, loader=1.0, processor=1.0
Sequencing
  sequencing_violation_count: 0
  sequencing_violation_blocks: 0
  sequencing_violation_days: 0
  sequencing_violation_breakdown: none
```

So that is promising in terms of getting "good" solutions pretty quickly from the MILP. 
