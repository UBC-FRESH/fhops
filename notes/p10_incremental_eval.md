# P10: Incremental evaluation and repair for the FHOPS SA solver

Status: active. Branch `feature/p10-incremental-eval`, off `merge/v101-into-main` (v1.1.0b1).
Builds on P9 (issue #165); the S4a lazy-evaluation change is already in.

## Why

After S4a, the SA loop is dominated by neighbour generation and the per-move repair, not by scoring.
Profile of large84 (30 iterations, 18.8 s):

| Region | Share |
|---|---|
| `generate_neighbors` | 66% |
| — RNG `_shuffle_with_getrandbits` | 32% |
| — per-candidate repair | ~34% (within the above) |
| `evaluate_schedule` (repair + score) | 26% |
| `slot_is_valid` (across both) | 17% |

The full objective walk alone is a small part. The real cost is that every move re-repairs and
re-scores the whole schedule: the repair scans all shifts × machines (`slot_is_valid` 1 M calls per
30 iterations) even when the move left the schedule covered, and the scorer walks every slot.

ws4 avoided this by making a move O(cells it touches). This phase does the same for FHOPS.

## Design

The objective is separable by block except for two couplings:

- **mobilisation and transitions**: per machine (a machine's block sequence);
- **landing capacity**: per (landing, shift slot), shared by the blocks on a landing.

Everything else — block remaining volume, per-(block, role) inventory, head starts, truckload
thresholds, per-slot hard penalties — is held per block by `SequencingTracker` and does not couple
blocks.

So the evaluator maintains, for the current schedule:

- `block_contrib[block_id]`: the block's delivered and leftover volume, its slot-level hard
  penalties, and its share of the landing load, obtained by replaying that block's slots in shift
  order;
- `machine_contrib[machine_id]`: mobilisation cost and transition count from the machine's block
  sequence;
- `landing_counts[(landing, shift)]`: the machines on each landing per slot, for the cap;
- the totals and the objective.

A move changes one or two `(machine, shift)` slots. The evaluator:

1. finds the affected blocks (the blocks in the changed slots), machines, and landings;
2. recomputes only those blocks' contributions (replaying their slots) and those machines'
   mobilisation;
3. adjusts the landing counts for the changed slots and the landing penalty;
4. updates the totals.

The repair is made incremental the same way: a move can only uncover the blocks it left, so the
repair visits the changed slots and their blocks, not the whole schedule. A coverage invariant
(per block, the number of assigned slots) makes "is anything uncovered?" O(1).

## Tasks

- P10.1 Parity harness. A test that builds random schedules and random single/dual-slot moves on the
  example ladder, and asserts the incremental evaluator matches `_score_plan` exactly (same
  objective, delivered, leftover, violations) for every move.
- P10.2 Incremental block contributions. `_score_block` and the block cache; totals.
- P10.3 Incremental machine contributions. Mobilisation and transitions from the machine sequence.
- P10.4 Incremental landing counts and penalties.
- P10.5 Incremental repair. Coverage invariant and a dirty-only repair that visits changed slots.
- P10.6 Wire into the SA loop with a fallback to the full path for any move the incremental path
  cannot price, and an option to disable it.
- P10.7 Benchmark and close-out. Gate the change on `benchmark_sa.py` and the parity harness.

## Acceptance criteria

- Parity: for random schedules and moves on tiny7, small21, med42, large84, the incremental
  evaluator equals `_score_plan` to within 1e-9, on objective and every component.
- The SA run at a fixed seed and budget produces the **same** objective and schedule as the current
  code (the incremental path must not change the search).
- At least 3x on large84 at equal iterations, and no regression on the smaller scenarios.
- All FHOPS gates green.

## Risks

- The tracker's per-slot state (`role_inventory_today`, `role_consumed_slot`) and the head-start
  waiver make a per-block replay subtle; the parity harness is the guard.
- The RNG shuffle (32%) is out of scope here because it changes the random stream; it is tracked
  separately.
