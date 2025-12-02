# Operational MILP Tractability Plan

## Context

- Med42 and larger datasets now sit much closer to full-horizon capacity after the recent work_scale increases (small ≈17/21 days, med ≈38/42, large ≈84/84 for heuristic makespans).
- Gurobi solves small21 to optimality (~5 seconds) but med42 stalls for many hours at default settings, even with 36 threads.
- Anecdotally, loosening the gap (e.g., `--gap 0.05`) should reduce runtime, but we don’t yet have confirmed measurements for med42—collecting that data is part of this plan.
- Goal: ensure `fhops solve-mip-operational` (and benchmarks) return a feasible plan with a controllable gap in a predictable amount of time (≤ 1 hour) for med42/large84.

## Plan

### [ ] 1. Capture baseline solver diagnostics
- [x] 1.1 Run med42 with `--debug --solver-option LogFile=med42_default.log --solver-option Threads=<current> --solver-option TimeLimit=600` (gap unset) to gather a Gurobi log (root presolve stats, early nodes). Stop once enough log info is captured if it hasn’t terminated. *(Completed: med42_default.log shows presolve cuts it to 55 k×56 k, incumbent rises to 37.4 k with 2.1 % gap after ~590 s.)*
- [ ] 1.2 Extract model statistics (variables, constraints, binaries) for tiny/small/med/large via the build step (`--debug`) to quantify the jump in size.
- [ ] 1.3 Identify whether Gurobi ever finds an incumbent on med42 at default settings and how quickly, using log timestamps (check med42_default.log for heuristics vs B&B timing).

### [ ] 2. Budgeted option sweep
- [ ] 2.1 Run med42 with staged options (`TimeLimit`, `MIPGap`, `Threads`, `Presolve`, `Heuristics`) and log objective/gap/runtime for each combination to map the time-vs-gap curve.
- [ ] 2.2 Repeat for small21 and large84 (short time limits) to understand scaling and choose sensible defaults per tier.
- [ ] 2.3 Document the “inflection point” (e.g., gap ≤5 % in ≤20 min) and recommend default CLI settings (`--gap 0.05`, `--solver-option TimeLimit=1800`, etc.).

### [ ] 3. Warm starts / incumbent injection
- [ ] 3.1 Add support for feeding heuristic assignments as a MIP start (e.g., `--incumbent assignments.csv`) by populating Pyomo `x`/`prod` with the heuristic plan before calling Gurobi.
- [ ] 3.2 Evaluate whether a good incumbent shrinks runtime or improves gap quality, especially when combined with a modest `TimeLimit`.

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
