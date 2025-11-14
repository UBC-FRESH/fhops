# Tabu Search Rework Plan

Status: Draft — diagnosing the current Tabu Search behaviour before retuning.

## Observed failure mode

- Long-horizon convergence sweeps (≥10 min targets) terminate within milliseconds.
- Telemetry shows `proposals` counts in the single digits and only one logged step per run.
- The loop exits before hitting the stall budget because `_evaluate_candidates` returns no options or every candidate move is tabu without aspiration. Net effect: the search explores only one or two neighbourhood moves, then stops.
- Quick instrumentation runs (`python - <<'PY' ...`) show `_neighbors` was producing only two candidates per step on both `med42` and `synthetic-large` (matching the two enabled operators, swap/move). `_evaluate_candidates` therefore evaluates at most two neighbours, so if both moves become tabu the solver immediately exits.
- Updated diagnostics (`tmp/tabu-diagnostics/neighbor_counts.csv`) now confirm that enabling `block_insertion`, `cross_exchange`, and `mobilisation_shake` as non-zero-weight operators yields five distinct candidates per step, removing the immediate “only two moves available” constraint.

## Current implementation (pseudocode)

```
solve_tabu(pb, iters, seed, operators, operator_weights,
           batch_size, max_workers, tabu_tenure, stall_limit):
    rng ← Random(seed)
    registry ← OperatorRegistry.from_defaults()
    apply operator filters / weights

    current ← init_greedy(pb)
    current_score ← evaluate(current)
    best ← current
    best_score ← current_score

    tenure ← tabu_tenure if provided else max(10, num_machines)
    tabu_queue ← deque(maxlen=tenure)
    tabu_set ← ∅
    stalls ← 0; proposals ← 0; improvements ← 0

    for step in 1..iters:
        candidates ← neighbors(pb, current, registry, rng, batch_size)
        evaluations ← evaluate_candidates(pb, candidates, max_workers)
        if evaluations is empty:
            break   # no move to consider

        best_candidate ← first candidate in evaluations sorted by score desc
                        such that move_signature ∉ tabu_set
                        unless aspiration (score > best_score)
        if best_candidate is None:
            break   # every move tabu without aspiration

        (candidate, score, move_sig) ← best_candidate
        current ← candidate; current_score ← score

        update tabu_queue and tabu_set with move_sig (drop expired entries)

        if current_score > best_score:
            best ← current; best_score ← current_score
            stalls ← 0; improvements += 1
        else:
            stalls += 1

        emit step telemetry if requested (step == 1, == iters, or multiple of interval)

        if stalls ≥ stall_limit:
            break   # stop after consecutive non-improvements

    build assignments from best solution, compute KPIs, emit telemetry, return payload
```

Key observations:

- There is no fallback diversification once every candidate is tabu; the run just stops.
- Stall tracking never increments if the loop exits early due to empty candidate sets.
- No wall-clock guard; the method uses raw iteration counts only, so a “long” run still ends immediately when no new candidate is accepted.

## Parameter snapshot and confidence

| Parameter | Current default / source | Selection rationale | Confidence in current value |
|-----------|-------------------------|---------------------|-----------------------------|
| `iters` (CLI `--iters`) | 2 000 (short tier), 3 000 (long tier) | Mirrors SA tier budgets for parity in harness. | **Low** — meaningless while the solver exits early; needs to correlate with real wall-clock once logic fixed. |
| `tabu_tenure` | `max(10, num_machines)` | Simple scaling with machine count to avoid empty tabu list on small cases. | **Low** — no data supporting 10; tenure should reflect neighbourhood size and diversification goals. |
| `stall_limit` | 200 (CLI default); experiments raised to 1 000 000 | Copied from SA medium horizon to limit time on plateaus. | **Low** — solver never reaches the limit; logic needs a two-phase stall strategy (per-move vs wall-clock). |
| `batch_size` | 1 unless tier overrides | Keep sequential neighbour scoring for determinism. | **Medium** — fine for now; not linked to failure mode. |
| `parallel_workers` | 1 unless profile overrides | Avoid multi-thread contention until benchmarks justify it. | **Medium** — unrelated to stall issue. |
| Operator weights | Registry defaults (`swap=1`, `move=1`, others 0) | Matches SA defaults after operator refactor. | **Low** — Tabu relies on diversification; using only swap/move severely limits neighbourhood exploration. |
| Step interval | 25 (context default) | Chosen for SA logging cadence. | **Medium** — telemetry works; problem is solver stopping too soon. |
| Aspiration check | `score > best_score` | Classic aspiration condition. | **Medium** — but because best_score rarely improves, equality is blocked, causing more early exits. |

## Next investigation steps

1. Instrument `_neighbors` / `_evaluate_candidates` to count generated candidates per operator and understand why the set is often empty.
2. Prototype forced diversification: when all moves are tabu, relax the list (e.g., drop oldest entry, random move, strategic oscillation) instead of breaking.
3. Revisit operator mix (enable insertion/cross-exchange/mobilisation) so Tabu can traverse more of the search space per step.
4. Introduce wall-clock budgets (or iteration milestones) independent of stall counts to keep the solver running for the requested duration.
