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
