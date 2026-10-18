# P10.6 tactical attack plan: incremental repair (`RepairState`)

Status: active. Branch `feature/p10-incremental-eval`. Issue #166.
Predecessors: P10.5 (lazy pre-repair) is banked; the profile after it:

| med42, 400 iters | share |
|---|---|
| `_score_lazily` (pre-repair + evaluate + score) | 77% |
| `_repair_schedule_cover_blocks` | 63% |
| `evaluate_schedule` (repair + score) | 61% |
| `slot_is_valid` | 23% |

Per-call cost of the repair: `fill_voids=True` (the evaluate repair) is **6–9x** the
`fill_voids=False` pre-repair (med42 4.3 vs 0.67 ms; large84 37.9 vs 4.2 ms) and changes 87–98% of
candidates. **The evaluate repair is the target.**

## Objective and acceptance

- A move repairs in O(slots it touches) instead of O(schedule).
- **Parity:** the incrementally repaired schedule equals the fully repaired schedule, slot for
  slot, on tiny7/small21/med42/large84, on random move chains. This is the gate; no speed claim
  without it.
- The SA run at a fixed seed and budget is unchanged.

## Why it is hard (the design constraint)

The repair walks every slot in order and, at each empty/invalid slot, fills from the *global*
remaining-volume state built up over all earlier slots. So the fill at day 40 depends on the fill at
day 3. Order-dependent and global — the opposite of the evaluator, which is a clean per-block sum.
The win therefore comes from **not re-walking slots before the earliest change**, which needs the
repair state to be recoverable at that point.

## Steps (each a bounded move, parity-guarded)

1. **`RepairState` dataclass.** Fields: `block_remaining`, `role_remaining`,
   `role_inventory_estimate`, `role_inventory_today`, `role_consumed_slot` (the five structures that
   live in the closure today). Add an optional `state=` to `_repair_schedule_cover_blocks`; when
   absent, create one as today; write it back on the schedule. Behaviour-neutral.
   Verify: repaired-schedule parity test.
2. **Slot snapshots.** The state evolves only at slot boundaries (`advance_slot`). Record a cheap
   per-slot snapshot (dict copies of the five structures, or a per-slot delta) in a list keyed by
   `shift_index`. Bound the cost: only the structures the fill reads.
   Verify: snapshotting alone does not change any result.
3. **`repair_from(state, slot_index)`.** Restore the snapshot at `slot_index` and re-run the main
   loop from there. The callers pass the earliest changed slot.
   Verify: `repair_from` from slot 0 equals the full repair; from an arbitrary slot equals a full
   repair on a schedule identical from that slot on.
4. **Wire into the SA loop.** A move changes a set of slots (`candidate.dirty_slots`); the repair
   starts at the earliest of them. Fall back to the full repair when the move touches a lock, a
   block window, or the landing state in a way the snapshot cannot express.
   Verify: SA parity (same objective and assignments) at fixed seed/budget on the ladder.
5. **Benchmark and close-out.** `benchmark_sa.py` before/after; record in the changelog; update the
   performance note.

## Risks and fallbacks

- **Snapshot overhead.** If copying the state per slot costs more than it saves on small horizons,
  store per-slot deltas instead, or snapshot only every N slots and re-walk the tail of a window.
- **Landing and locks.** The hard landing guard and locked slots add per-slot state
  (`landing_done`, `pending_lock_landing`); a move that changes a landing may invalidate the
  snapshot. Fall back to the full repair for those moves.
- **Correctness.** The parity test is the contract. If a step cannot pass it, revert that step and
  record why; do not weaken the test.

## Out of scope

- The RNG stream (ADR 0003 covers the cross-exchange change).
- The pre-repair (`fill_voids=False`); it is already cheap (0.67 ms on med42).

## Outcome (2026-10-18): shipped, default on

The incremental repair is implemented, exact, and now the default. Three bugs/fixes got it there:

1. `role_remaining_lookup` was bound before `RepairState` is created and aliased; on resume it kept
   pointing at the fresh dict, so the production cap read full volumes (day-5 med42: 1299 vs 356).
   Bound after the aliasing -> `resume@0 == full` on all four scenarios.
2. `build_sanitizer` returned a fresh `schedule_cls(plan=plan)` and dropped the operator's
   `_set_slot` dirty marks, so candidates had `dirty_slots == set()` and the resume never fired. It
   now carries the input dirty sets and adds the cells it drops.
3. The resume takes the full snapshot list (indexed by slot) and carries the parent prefix, so the
   accepted candidate already has snapshots -- no full repair per acceptance.

Measured (5 seeds): tiny7 1.00x, small21 0.99x, med42 1.06x, large84 1.14x; objectives and exported
assignments byte-identical. The guards in `solve_sa` fall back to the full repair when the
equivalence is not guaranteed (`batch_size` + parallel workers, `pre_repair=False`,
`use_local_repairs=True`), and the pinned fixtures regenerate with no diff.
