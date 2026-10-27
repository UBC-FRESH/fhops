# NVIDIA cuOpt MIP pilot

Date: 2026-10-27
Issue: #168
Status: rejected for adoption; no production backend
Related: #169 (`feasible_start`), `notes/mip_tractability_plan.md`
Paper context: `UBC-FRESH/fhops-cjfr-rolling-horizon`

## Evidence sources

This memo consolidates evidence already recorded during the 2026-10-18 to
2026-10-20 pilot. It does not add new cuOpt runs.

- #168 issue comments (2026-10-18, 2026-10-19, 2026-10-20): Nibi environment,
  med42, pg_40, and the equal-total-budget correction.
- #169 and its merged PR: `feasible_start`, the fixed-binary LP that makes a
  heuristic plan a usable MIP start.
- `UBC-FRESH/fhops-cjfr-rolling-horizon`, `results/seeding/PROVENANCE.md` and
  `results/seeding/equal_total_pg40.jsonl`: the committed equal-total evidence
  behind the paper's Limitations sentence.
- `UBC-FRESH/fhops-cjfr-rolling-horizon`, `CHANGE_LOG.md` (2026-10-20) and
  `manuscript/sections/discussion.tex`: how the paper uses the result.
- `notes/mip_tractability_plan.md`: earlier warm-start experiments; its
  "not yet practically useful" conclusion is superseded by #169 and the
  equal-total evidence.

## Question

On representative FHOPS operational MILPs, does NVIDIA cuOpt reach a given
incumbent quality faster than cold-started Gurobi, and/or reach a better
incumbent at a fixed time budget?

The motivation was the CJFR rolling-horizon bottleneck: in the largest cells,
cold-started Gurobi can spend most of its 1,800 s window without a usable
incumbent. cuOpt's beta MIP solver advertises GPU-accelerated primal
heuristics, which is the relevant bottleneck; optimality proofs are not.

## Environment and deviation

The pilot ran on Nibi GPU partitions (H100/MIG, A100, MI300A; CUDA 12.9 and
13.2) using an Apptainer container, not on Sockeye as originally scoped. The
pip route failed because the cuOpt Python packages require the full RAPIDS
stack (`cuopt-server-cu12` -> `cuopt-cu12` -> `cudf-cu12`) and no matching
distribution resolved in a plain virtual environment. The working path was
`apptainer pull docker://nvidia/cuopt:26.10.0-cu12` and
`apptainer exec --nv`.

The issue comments record the run results. A Slurm job ID and `nvidia-smi`
capture were not retained, so the original Sockeye acceptance artefacts are
only partially met. This does not affect the adoption decision: the comparison
is large enough to reject cuOpt and the remaining formal artefact would not
change that recommendation.

The pilot also tested cuOpt as a **seed source**, not as a full replacement for
the Gurobi operational MILP. cuOpt produced candidate schedules; `feasible_start`
made them MILP-feasible; Gurobi then solved the operational MILP. The comparison
answers whether cuOpt's GPU primal heuristics beat the FHOPS CPU heuristics as a
warm start. It does not claim cuOpt was productionised as a solver backend.

## Method

Every heuristic arm was converted into a Gurobi MIP start with `feasible_start`:
fix the assignment binaries, solve the LP for the flows, then hand the result to
Gurobi. The cuOpt seed comparison used seed 42 and one instance per size. The
separate `feasible_start` evidence in #169 also ran the ILS seed on med42 across
three seeds and reached 28,322–28,504, so the ILS result is not a one-seed
fluke.

- `med42`: 300 s MIP budget; compare cold start with greedy, SA, ILS, and cuOpt
  seeds.
- `pg_40` full horizon: 300 s MIP budget for the seed-source comparison.
- `pg_40` full horizon: equal **total** budget of 1,800 s per arm. This is the
  fair framing because the seed time is charged against the MIP time.

The original issue listed `tiny7` and `med42`; the observed pilot used `med42`
and `pg_40`. `tiny7` was not part of the recorded comparison.

## Results

### med42, 300 s MIP budget

| Arm | Seed wall (s) | Gurobi objective | Total (s) |
| --- | ---: | ---: | ---: |
| cold | 0 | 21,916.36 | 302 |
| greedy + LP | ~2 | 23,978.02 | 304 |
| SA (2,000 iters) + LP | 101 | 26,858.01 | 403 |
| **ILS (50 iters) + LP** | **7.0** | **28,322.17** | **309** |
| cuOpt (GPU, 300 s) + LP | 307 | 28,337.83 | 609 |

The FHOPS ILS seed matched a 300 s GPU cuOpt seed to 0.06% while using about 2%
of the wall time.

### pg_40 full horizon, 300 s MIP budget

| Arm | Seed wall (s) | Gurobi objective |
| --- | ---: | ---: |
| cold | 0 | -1,309,443.40 |
| ILS (50 iters) + LP | 1,206.8 | **+254,042.21** |
| cuOpt (GPU, 375 s) + LP | 374.7 | -922,398.20 |

At a 300 s MIP budget the cold arm had no usable incumbent, while ILS + LP
reached a positive objective. cuOpt improved on cold but was far behind ILS.

### pg_40 full horizon, equal total budget (1,800 s)

| Arm | Seed wall (s) | LP (s) | MIP (s) | Total (s) | Objective | MIP gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **cold** | 0 | – | 1,828 | 1,828 | **392,699.08** | **0.7434%** |
| greedy + LP | 10.4 | 17.2 | 1,797 | 1,825 | 391,541.56 | 1.0412% |
| SA (108 iters) + LP | 1,133.4 | 15.9 | 675 | 1,824 | 389,954.89 | 1.4523% |
| ILS (50 iters) + LP | 1,081.8 | 16.6 | 725 | 1,823 | 390,139.35 | 1.4043% |
| Tabu (104 iters) + LP | 1,094.5 | 16.6 | 712 | 1,823 | 390,685.60 | 1.2626% |

All seeded starts were verified as loaded by Gurobi. At equal total budget,
cold has the best objective and gap. The objective spread among arms is at most
about 0.7%, so seeding is a wash for final quality. The raw committed rows are
in the paper repository's `results/seeding/equal_total_pg40.jsonl`.

This equal-total experiment compared CPU seed sources (greedy, SA, ILS, Tabu),
not cuOpt. cuOpt was rejected on the separate seed-quality comparison: its
GPU seed cost hundreds of seconds and did not beat the 7 s ILS seed. The
equal-total result additionally shows that, even if the GPU seed were free,
seeding would not improve final quality at the paper's budget.

## Findings

1. cuOpt is not competitive with the built-in FHOPS ILS as a seed. The ILS is
   CPU-only, open source, reproducible, and far faster on the tested instance.
2. In the equal-total CPU-seed experiment at the study's 1,800 s budget, cold
   Gurobi is at least as good as every seeded arm. The earlier "cold is
   catastrophic" result was a 300 s artefact. cuOpt was not part of that
   equal-total run; it was already dominated at the seed stage.
3. The real measured benefit of seeding is **early feasibility**: a usable
   incumbent around 0.5 s versus cold's first improving incumbent at 410 s on
   `pg_40`. It is a deadline and no-solution-window fix, not a scale fix.
4. `feasible_start` is worth keeping because it makes any seed usable as a MIP
   start. It is implemented in #169; it is not a cuOpt feature.
5. The paper's Limitations sentence is deliberately narrow: seeding buys early
   feasibility, not scale or final quality at equal total budget. This memo does
   not change the manuscript or the banked results.

## Decision

**Do not adopt cuOpt and do not add a production cuOpt solver backend.** Keep the
workflow CPU-only with Gurobi/HiGHS, the built-in heuristics, and
`feasible_start` as the warm-start path. The measured benefit from seeding is
early feasibility, not final quality or scale.

## Revisit conditions

Revisit only if all of the following hold:

- cuOpt MIP is out of beta and reports a stable gap/optimality status;
- there is a supported Pyomo/MPS-to-cuOpt path, or a maintained algebraic
  exporter that preserves the operational formulation;
- the GPU memory and container/licence path is available on the target cluster;
- an equal-total-budget benchmark on `med42` and `pg_40`, with multiple seeds,
  shows a clear advantage over cold Gurobi and the built-in heuristics.

## Limits

- One instance and one seed per comparison; `pg_40` is a single size-40 case.
- The pilot ran on Nibi, not Sockeye; job-ID and `nvidia-smi` artefacts were not
  retained in the issue comments.
- No `tiny7` comparison was recorded.
- cuOpt was used as a seed source, then Gurobi solved the MILP; this is not a
  full head-to-head cuOpt-as-solver run.
- cuOpt MIP was beta; results may not carry forward to later releases.
- No production export path, backend, release, or manuscript change was made.
- No real watershed or regulatory result is involved.
