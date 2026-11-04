# Shared metaheuristic kernel adapter

Status: proof of concept (2026-11-03)
Related: `AGENTS.md`, `notes/metaheuristic_roadmap.md`, ADR 0007 in WS4

## Decision

FHOPS will consume the problem-agnostic search kernel from `fresh-solutions` rather than
maintain a second copy of the solvers. FHOPS keeps its domain layer: the machine-by-slot
`Schedule`, repair/sanitizer, sequencing, landing and mobilisation rules, objective weights,
telemetry, tuning, and the MIP hybrid.

The adapter lives in `fhops.optimization.meta`:

- `FhopsProblem` subclasses the kernel `Problem[Schedule, FhopsContext]`.
- `FhopsContext` carries the parsed scenario and `OperationalProblem` lookups.
- `FhopsOperator` wraps a FHOPS operator and builds its `OperatorContext` per proposal.
- `slot_diff` is the tabu signature: the changed `(machine, day, shift)` slots.
- `solve_kernel_sa` exposes kernel simulated annealing with a FHOPS-compatible result
  (`objective`, `assignments`, `meta`, `schedule`).

The kernel minimizes, so the adapter negates the FHOPS score internally and reports the fresh
positive FHOPS objective after the run.

## What is not done yet

- Kernel SA, Tabu, and ILS all use one proposal per iteration; the existing FHOPS solvers sample
  batches per step. The adapter is an integration proof, not yet a behaviour-parity replacement.
- The fast path avoids the kernel's deep state copy and uses dirty-slot repair, but it is not a
  true delta evaluator.
- `solve_kernel_sa_incremental` uses the existing block-separable `SeparableEvaluator`, with
  reversible move scoring (`undo_last_move`). It matches the full objective exactly on Tiny7,
  Small21, and med42 and is faster on larger scenarios.
- A true in-place FHOPS move/undo record is still the next step; the current incremental path
  copies the sanitized candidate and then updates the evaluator cache.
- Telemetry, tuning, and watch integration still use the FHOPS implementations.
- Parity gates: Tiny7, Small21, Jaffray, med42, and the synthetic scaling tiers, plus the #151
  performance envelope.

## Evidence

`tests/meta/test_kernel_adapter.py` checks the registry, operator wrapper, slot signature, a
replayable assignment table (the planned score equals `evaluate_assignments`), operator
restriction, and the empty schedule. `tests/heuristics` remains green.

## Parity and performance evidence (2026-11-03)

- Kernel SA, Tabu, and ILS all return an assignment table whose planned score equals
  `evaluate_assignments`; the Tiny7 scenario gate runs each path and checks that identity.
- Reproduce with `PYTHONPATH=src python scripts/benchmark_kernel_paths.py`.
- Tiny7, 200 iterations, seed 7, local timing:
  - kernel SA (deep-copy state, full repair): 0.118 s, objective -2673.433;
  - kernel SA fast path (operator-level patch copy, dirty-slot repair): 0.103 s,
    objective -2646.813.
  The fast path was ~13% quicker in this run (23% in the earlier run). It is not equal-work or
  a parity claim: the search score is approximate and the returned objective is freshly and
  fully rescored.
- Behaviour parity with the existing FHOPS SA/Tabu/ILS loops is **not yet claimed**. The kernel
  paths use one proposal per iteration; the existing solvers sample batches and carry more
  telemetry/watch/tuning state.


## Incremental block-separable path (2026-11-04)

`solve_kernel_sa_incremental` repairs each candidate, scores only the blocks touched by
`slot_diff`, and rolls the evaluator cache back on rejection. The returned schedule is always
rescored with `evaluate_schedule`.

Tiny7, 200 iterations, seed 7:

| Path | Seconds | Objective |
| --- | ---: | ---: |
| full kernel SA | 0.157 | -2673.433 |
| dirty-repair fast path | 0.109 | -2646.813 |
| block-separable incremental | 0.108 | -2673.433 |

100-iteration comparison at the same seed:

| Scenario | Full seconds | Incremental seconds | Objective |
| --- | ---: | ---: | ---: |
| small21 | 0.214 | 0.196 | 8402.789 |
| med42 | 0.515 | 0.355 | 20543.16 |

The incremental path is the preferred kernel path: same objective as full scoring, lower cost.

## Objective-weight parity (2026-11-04)

`FhopsProblem` now applies `resolve_objective_weight_overrides` and `override_objective_weights`,
so the kernel paths use the same built-in Tiny7/Small21 overrides as the existing FHOPS solvers
(`production=1.0`, `mobilisation=0.2`, `transitions=0.1`, `landing_surplus=0.05`) and honour
explicit overrides. The applied mapping is recorded in every kernel result's `meta`.

The Tiny7 scenario gate now rescored through the overridden context, and a dedicated test checks
both the automatic mapping and an explicit override.


## Parity ladder (2026-11-04)

`scripts/compare_kernel_solvers.py` runs the existing FHOPS solver and the kernel path with the
same scenario, seed, and 100-iteration budget. Raw records:
`notes/reference/kernel-parity-2026-11-04.json`.

| Scenario | Solver | Existing | Kernel | Delta | Kernel speed ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| tiny7 | SA | 4295.775 | 4338.517 | +42.742 | 0.34 |
| tiny7 | Tabu | 4338.517 | 4338.517 | 0.000 | 1.15 |
| tiny7 | ILS | 4338.517 | 4338.517 | 0.000 | 0.18 |
| small21 | SA | 15551.329 | 15508.871 | -42.458 | 0.37 |
| small21 | Tabu | 15563.091 | 15583.627 | +20.536 | 1.12 |
| small21 | ILS | 15584.345 | 15562.417 | -21.928 | 0.16 |
| med42 | SA | 20898.340 | 20543.160 | -355.180 | 0.35 |
| med42 | Tabu | 22444.217 | 22045.206 | -399.011 | 0.84 |
| med42 | ILS | 23572.070 | 19349.545 | -4222.524 | 0.07 |

The kernel paths are competitive and usually faster, but they are not trajectory-identical. The
kernel ILS is not like-for-like: the existing FHOPS ILS runs a local-search/perturbation loop, while
the kernel ILS is the kernel's perturb-and-accept loop. The existing FHOPS solvers stay in place
until a like-for-like ILS and a full ladder (Jaffray and the synthetic scaling tiers) pass.


## Scaling ladder (2026-11-04)

50 iterations, seed 7. The same raw record file carries the scaling rows.

| Scenario | Solver | Existing | Kernel | Delta | Kernel speed ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| large84 | SA | -213942.207 | -221802.325 | -7860.118 | 0.27 |
| large84 | Tabu | -218267.868 | -206134.176 | +12133.692 | 0.65 |
| large84 | ILS | -204723.129 | -223809.013 | -19085.884 | 0.04 |
| synthetic/small | SA | 39.791 | 39.791 | 0.000 | 0.32 |
| synthetic/small | Tabu | 39.791 | 39.791 | 0.000 | 1.08 |
| synthetic/small | ILS | 39.791 | 39.791 | 0.000 | 0.20 |
| synthetic/medium | SA | 61.887 | 61.887 | 0.000 | 0.32 |
| synthetic/medium | Tabu | 61.887 | 61.887 | 0.000 | 1.03 |
| synthetic/medium | ILS | 61.887 | 61.887 | 0.000 | 0.18 |
| synthetic/large | SA | 46.839 | 46.839 | 0.000 | 0.40 |
| synthetic/large | Tabu | 64.007 | 46.839 | -17.168 | 1.00 |
| synthetic/large | ILS | 64.007 | 46.839 | -17.168 | 0.17 |

The synthetic tiers agree exactly on SA and mostly on Tabu/ILS; the large84 Tabu kernel result is
worse by ~5.6% and reinforces that the existing solvers stay until a like-for-like ILS and the
retirement decision.


## Like-for-like ILS ladder (2026-11-04)

`solve_kernel_ils_like` mirrors the existing FHOPS ILS: one candidate per enabled operator per
local-search pass, best improvement accepted, random perturbation between passes, restart from the
incumbent at the stall limit. 50 iterations, seed 7; raw records:
`notes/reference/kernel-parity-ils-2026-11-04.json`.

| Scenario | Solver | Existing | Kernel | Delta | Kernel speed ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| tiny7 | ILS (existing semantics) | 4338.517 | 4338.517 | 0.000 | 0.64 |
| small21 | ILS (existing semantics) | 15573.545 | 15551.187 | -22.358 | 0.63 |
| med42 | ILS (existing semantics) | 21662.981 | 20762.835 | -900.146 | 0.56 |

The like-for-like kernel ILS is slower than the plain kernel ILS (which is a different algorithm)
but closer to the existing ILS. It matches Tiny7 exactly and improves Small21/med42 at this budget;
it is not trajectory-identical, so the existing solver stays until a longer multi-seed ladder passes.
