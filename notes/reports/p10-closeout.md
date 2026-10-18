# Phase close-out report: FHOPS SA performance (P9/P10) and the 1.1.0b1 tactical merge

Phase: P9 simulated-annealing performance and P10 incremental evaluation/repair, delivered together
with the v1.0.1-into-`main` merge.
Parent issues: #164 (merge v1.0.1 into `main`, targets 1.1.0b1), #165 (P9 SA performance),
#166 (P10 incremental evaluation and repair).
Pull request: #167, `feature/p10-incremental-eval` into `main`.
Evidence head: `15e521cd7056468236304a7bfb1b5c3db2c7acc3`. The gates below were run before the
report; the first CI run on the branch exposed a formulation-check bug (see Deviations), fixed in
the evidence head.
Report commit: the tip of this branch (see PR #167). Its CI run is posted on #167 and on the issues.
Date: 2026-10-18
Status: queued for approval. Nothing is merged, tagged, released, or changed in repository settings.

## Recommendation

Approve these actions. The agent carries them out in this order and reads back each result. Each
item can be approved or declined on its own.

1. Merge #167 into `main` with a **merge commit** (not squash), so the v1.0.1 line and the
   `v1.1.0b1` release merge (`a6ccabb`) keep their history. `main` (`ff7c51a`) is an ancestor of the
   branch tip, so the merge is clean.

   ```bash
   gh pr merge 167 -R UBC-FRESH/fhops --merge --match-head-commit <branch tip at approval>
   ```

2. Delete the remote branch `feature/p10-incremental-eval`.

   ```bash
   git push origin --delete feature/p10-incremental-eval
   ```

3. Close #164, #165 and #166 with close-out comments that cite the merge commit and this report.

Deferred, named for a separate approval (not part of this report):

- Tag `main` as `v1.1.0b2` and create a GitHub release, if the maintainer wants a fresh prerelease
  after the P9/P10 performance work.
- Publish to PyPI/TestPyPI (see `notes/release_candidate_prep.md`).

## Objectives and acceptance

- #164: bring the v1.0.1 operational corrections into the tactical line as `1.1.0b1`. **Met** — merge
  commit `a6ccabb`, recorded in `d3cdd34`, tagged `v1.1.0b1`.
- #165: raise SA throughput without changing results. **Met** — S4a lazy candidate evaluation (2.1x,
  identical objectives); S2 (dirty-only repair) dropped, S3 (nested hot path) reverted, both recorded
  in `notes/sa_performance_plan.md`.
- #166: make the per-move repair incremental and exact. **Met** — block-separable evaluator, bounded
  `cross_exchange` (ADR 0003), lazy pre-repair, and the incremental repair now the default.

## Evidence

- Tests: `pytest` 914 passed, 214 skipped. `mypy src` clean (128 files). `ruff check src tests
  scripts` clean.
- Byte-identical default: `python scripts/regenerate_sa_baselines.py` rewrites the pinned `*_v101.csv`
  tables and `baseline.json` entries with **no diff**; a 4-scenario x 6-config x 3-seed parity matrix
  is 72/72 identical to `incremental_repair=False`.
- Speed (200 iterations, same host, 3 seeds, iterations/s — higher is better):

  | scenario | 1.1.0b1 base (`a6ccabb`) | branch tip | session |
  |---|---|---|---|
  | tiny7 | 301.6 | 689.0 | 2.28x |
  | small21 | 69.9 | 251.2 | 3.59x |
  | med42 | 20.5 | 98.7 | 4.81x |
  | large84 | 2.2 | 9.0 | 4.14x |

  Geometric mean of the session speedup: ~3.6x. Today's increment (P10.5 + P10.6) is ~1.48x,
  geometric mean, with byte-identical results.
- The adaptive (Aarts & Van Laarhoven) cooling schedule is ported, tested, and **opt-in only**
  (`adaptive_cooling=False`); a tuning study found it is not a robust default
  (`notes/sa_performance_plan.md`).

## Workflow compliance

- Parent issues and child work exist; the ADR (0003) is committed; `ROADMAP.md`, `CHANGE_LOG.md`, and
  the SA notes are updated with the phase.
- This report is committed to `notes/reports/` in the phase branch, per ADR 0008.
- The merge, branch deletion, and issue closures are queued here and executed only after approval.

## Deviations and risks

- The branch bundles #164, #165 and #166 (it grew from the 1.1.0b1 integration branch). A single PR is
  a deviation from one-PR-per-child; the alternative (splitting) would lose the merge base.
- P10.3 deliberately changed the SA random stream (ADR 0003), so SA objectives differ from the
  pre-ADR base; the pinned baselines were regenerated. The CJFR manuscript is unaffected (its SA
  results were produced on the separate FHOPS 1.0.1 line).
- Populating the sanitizer's dirty marks also changes the default-off, previously dropped
  `use_local_repairs=True` path; that mode is documented as approximate and is in no pinned result.
- The CJFR manuscript repository depends on FHOPS 1.0.1, not on this branch.
- The first CI run on the branch (this PR) failed the formulation asset drift check: the exporter
  printed `path.relative_to(repo_root)` on a temporary render path. Fixed in the evidence head
  (display-only; the generated assets are unchanged).

## Recommended next steps

1. Approve and execute items 1–3 above.
2. Decide on the deferred `v1.1.0b2` tag/release.
3. Return to the CJFR manuscript wrap-up (P1.1 final analysis, then P2 data release).
