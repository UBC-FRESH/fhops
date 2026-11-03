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

- Kernel SA is one proposal per iteration; the existing FHOPS SA samples a batch per step. The
  adapter is an integration proof, not yet a behaviour-parity replacement.
- Tabu and ILS adapters are next; the delta path needs an in-place FHOPS move/undo record.
- Telemetry, tuning, and watch integration still use the FHOPS implementations.
- Parity gates: Tiny7, Small21, Jaffray, med42, and the synthetic scaling tiers, plus the #151
  performance envelope.

## Evidence

`tests/meta/test_kernel_adapter.py` checks the registry, operator wrapper, slot signature, a
replayable assignment table (the planned score equals `evaluate_assignments`), operator
restriction, and the empty schedule. `tests/heuristics` remains green.
