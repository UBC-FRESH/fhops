# SA performance plan (FHOPS, merged 1.1.0b1 base)

Status: active. Branch `feature/sa-performance-v2`, off the v1.0.1-into-main merge (`a6ccabb`,
version `1.1.0b1`). Supersedes the exploratory assessment in the earlier note.

## Goal

Bring the FHOPS simulated-annealing solver (`src/fhops/optimization/heuristics/`) to the speedups
demonstrated in ws4 (about 1 to 5000 evaluations/s on a production-scale benchmark), without
changing the objective, the operators, or the schedules a run produces at a fixed seed and budget
beyond what a faster search legitimately explores.

## Baseline (merged 1.1.0b1, med42: 9 machines, 12 blocks, 42 days)

| Setting | Rate | Objective |
|---|---|---|
| Default (full repair per move) | 21.3 evals/s | 21141.7 at 200 iters |
| `use_local_repairs=True` | 34.0 evals/s | 15605.6 at 200 iters |

`cProfile` (100 iters, default): `_repair_schedule_cover_blocks` is 70 percent of runtime
(9.0 s of 12.7 s), reached through `slot_is_valid` (1.2 M calls), `select_block`,
`reserve_downstream_landings` (21 k calls, 2.0 s), and `record_assignment`; `generate_neighbors` is
another 31 percent; the hot loops make 14 M `dict.get` calls. The objective walk itself is minor.

## Acceptance criteria

- On the benchmark ladder (tiny7, small21, med42, large84), the default solver reaches at least 10x
  the current evaluations/s at the same iteration budget.
- The objective at a fixed seed and budget is no worse than the baseline (quality is not traded for
  speed without a recorded decision).
- Every optimization has a parity test: the fast path reproduces the reference objective and
  schedule on random inputs, to a stated tolerance.
- `scripts/benchmark_sa.py` reports evaluations/s, objective, and peak memory per scenario, and the
  figures go in `notes/performance_sa.md`.
- All FHOPS gates stay green: `ruff format --check src tests`, `ruff check src tests`, `mypy src`,
  `pytest`.

## Tasks, in priority order

### S1 Baseline harness and guardrail
A benchmark script over the ladder, a documented baseline, and a fast parity test that the local
repair produces the same final objective as the full repair after the final re-score.
Verification: script output recorded; parity test passes.

### S2 Dirty-only repair by default
Make the existing `use_local_repairs` path the default (auto-enabled above a size threshold), keep
the final full re-score, and validate quality across the ladder at fixed budgets.
Expected: ~1.6x. Verification: benchmark + objective comparison.

### S3 Static caching and hot-loop cleanup
Cache the per-(machine, block) rates, landing, availability, role priority, ordered machines, shift
keys, and per-block candidate lists on the schedule context; remove repeated `dict.get` in the inner
loop. Expected: 1.5-2x on top of S2. Verification: benchmark + unit tests for the caches.

### S4 Incremental repair and evaluation
Maintain the running state (per-(role, block) inventory, delivered and remaining volume, per-machine
last block, landing-per-shift counts) so a single-slot move is priced by its exact delta, in the ws4
mould, and repairs only the dirty slots. Fall back to the full path for operator types it cannot
price. This is the change that closes most of the gap. Expected: 5-50x.
Verification: parity test against the full evaluator on random schedules; benchmark.

### S5 Vectorize the repair and evaluation loops
Use numpy for the per-shift repair and the evaluation walk where the state permits. Expected:
additional. Verification: benchmark + parity.

### S6 Process-parallel multistart and islands
Replace thread-batched candidate scoring with process-parallel independent searches and an island
model with elite migration. Throughput and quality. Verification: benchmark + quality comparison.

### S7 Documentation and close-out
Performance page, changelog, and a close-out report.

## Notes and risks

- The objective must not change. Any change in the objective is a separate, reviewed decision.
- `use_local_repairs` already exists and is safe; the risk in S2 is search-trajectory change, which
  is why the parity test is about the final re-score, not the intermediate trajectory.
- ws4's negative results transfer as guidance: native kernels are not needed until the Python cost is
  gone, and threads are a dead end for CPU-bound Python (GIL); processes are the lever.


## Results so far (2026-10-17)

| Task | Result |
|---|---|
| S1 harness | done; baseline tiny7 281, small21 72, med42 21.2, large84 2.2 evals/s |
| S4a lazy candidate evaluation | **done, 2.1x** (tiny7 580, small21 167, med42 44.4, large84 3.4), objectives byte-identical |
| S2 dirty-only repair default | measured: mixed (tiny7 1376, small21 144 worse, med42 47.9, large84 3.4). **Dropped**: needs a size gate, breaks pins, no consistent gain |
| S3 nested-dict hot path | measured: slightly worse on every scenario (the per-call rebuild and two-level lookup cost more than the tuple hashes). **Reverted** |

Remaining headroom is the per-move repair itself and the RNG shuffle (~18 percent, constrained by
the pinned random stream). Both need a larger, separately scoped change (an incremental evaluator
with parity tests) rather than a tweak. Stopped the side-quest after S4a.

## Adaptive cooling study (2026-10-18)

Ported the Aarts and Van Laarhoven (1985) adaptive schedule from ws4
(`src/fhops/optimization/heuristics/cooling.py`) and wired it into `solve_sa` as opt-in
(`adaptive_cooling`, `cooling_window`, `cooling_initial_acceptance`, `cooling_delta`). The default
path (geometric, `temperature *= cooling_rate`) is unchanged, so the pinned baselines are untouched.

Harness: `scripts/benchmark_sa_cooling.py`. It records the best-so-far curve every iteration through
`watch_sink` and reports the objective at fixed iterations and interpolated at equal wall-clock.

### Findings (5-8 seeds, seed 42 family)

| Scenario | Geometric final | Adaptive best (window) | Verdict |
|---|---|---|---|
| med42 (iters 300) | 21046 | **22286** (w=8) | adaptive clearly better at equal iterations and equal time |
| large84 (iters 200) | **-210111** (8 seeds) | -209247 (w=8), -215603 (w=16) | geometric better at long budgets; adaptive converges earlier |

- The **window dominates**; the auto default (`64`) is far too large when `iters` is only a few
  hundred (the schedule gets ~2 cooling steps). Medium scenarios want `window ~ 8`.
- On large84 the adaptive accepts more (fewer candidate evaluations, ~1.5-2x faster per iteration)
  but converges to a worse objective; the geometric's `T0 = max(1, best/10)` floors at 1.0 for the
  negative-objective scenarios and that cold schedule is actually good there. Confirmed by
  experiment: making the geometric scale-aware (`abs(best)/10`, i.e. hot) made large84 *worse*
  (-217798 vs -208717), so a hot start is not the answer for the large instance.

### Recommendation

**Keep adaptive cooling opt-in, do not enable by default.** It is a real win for medium scenarios
(and a modest per-iteration speedup everywhere), but it is not a robust improvement on the largest
scenario, and it would change every pinned SA result. Before any default-on decision: more seeds,
an equal-wall-clock "iterations-to-target" harness across the full ladder, a rule that scales the
window with `iters` and the objective scale, and the usual re-pin (ADR 0003 discipline).

## Incremental repair (P10.6, 2026-10-18) — shipped as the SA default

The per-move repair was the remaining hot spot; P10.6 resumes it from the accepted schedule's
per-slot state instead of re-repairing the horizon. It is exact and now the default
(`incremental_repair=True`), with automatic fallback to the full repair where equivalence is not
proven (batch parallel, `pre_repair=False`, `use_local_repairs=True`). Speedup (5 seeds): tiny7
1.00x, small21 0.99x, med42 1.06x, large84 1.14x; the pinned fixtures regenerate with no diff. See
`notes/p10_repair_refactor.md` for the root causes and the parity contract.

A first, orthogonal experiment with the adaptive cooling schedule is recorded above; it stays
opt-in.
