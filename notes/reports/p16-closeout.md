# Phase close-out report: P16 Flood-aware operational constraints

Phase: P16 Flood-aware operational constraints
Parent issue: #235
Pull request: #255, `feature/phase16-flood-operational-constraints` into `main`
Evidence head: `339d35b4` (P16.5 plus the `origin/main` cuOpt-memo merge)
Date: 2026-10-27
Status: queued for approval. Not merged.

## Recommendation

Approve these actions. The agent carries them out in this order, and reads back
each result.

1. Treat the phase pull request as the single P16 pull request.
2. Squash-merge it into `main` and delete
   `feature/phase16-flood-operational-constraints`.
3. Close the P16.5 issue and parent issue #235 with closeout comments that cite
   the merge commit.
4. Do not start a solver-side flood constraint. Keep enforcement at the tested
   one-schedule check layer until a single shared block/day availability hook
   exists.

Settings changes, each with its exact command. Each one runs only after its own
approval.

- None.

## 1. Objectives and acceptance

| Criterion | Evidence | Status |
| --- | --- | --- |
| Fixed hazard windows validate by watershed/day, severity, review, and overlap. | `fhops.scenario.hydrology_hazard`; P16.1 tests; PR #241. | Met |
| Explicit road/culvert assets map to scenario road jobs and FEMIC watersheds. | `fhops.scenario.hydrology_assets`; P16.2 tests; PR #243. | Met |
| One schedule reports watch/warning/closure exposure. | `fhops.scenario.hydrology_constraint_check`; P16.3 tests; PR #244. | Met |
| Closure activity fails by default; warning failure is an explicit policy. | `constraint-check` defaults and tests. | Met |
| Solver integration is only attempted where one shared hook supports it. | P16.4 audit; no partial solver patch; PR #245. | Met with a stated limit |
| The end-to-end CLI path is proven on a synthetic fixture. | `tests/scenario/test_hydrology_operational_integration.py`. | Met |
| No watershed flood model, flood map, or regulatory result is claimed. | This report, docs, and screen caveats. | Met |
| FHOPS quality suite and docs build are green. | Section 3. | Met |

## 2. Workflow compliance

- Parent issue #235 existed before the Phase 16 branch.
- Phase branch: `feature/phase16-flood-operational-constraints`.
- Child issues #236-#240 are linked as sub-issues. #236-#239 are merged and
  closed; #240 is this closeout.
- Child PRs: #241, #243, #244, #245.
- The phase note is `notes/phase16_flood_operational_constraints.md`.
- Roadmap, changelog, note, and issue bodies were kept in step.
- One final phase pull request carries the branch into `main`.
- No tag, release, visibility, or settings change is included.

## 3. Gate evidence

Local gates on the closeout branch:

- Full `pytest -q`: exit 0.
- `ruff format --check src tests`: clean.
- `ruff check src tests`: clean.
- `mypy src`: clean.
- `pre-commit run --all-files`: passed.
- `sphinx-build -b html docs _build/html -W`: succeeded.

Child CI runs:

| Task | PR | CI run | Result |
| --- | --- | --- | --- |
| P16.1 | #241 | 40543652939 | green |
| P16.2 | #243 | 40549897029 | green |
| P16.3 | #244 | 40557440975 | green |
| P16.4 | #245 | 40565514364 | green |

## 4. CI evidence

| Run ID | Head commit | Conclusion | Notes |
| --- | --- | --- | --- |
| pending | report commit | not yet run | CI runs on #255 after the report update. |

## 5. Deviations

| Deviation | Cause | Remedy |
| --- | --- | --- |
| Solver-side closure constraints were not implemented. | No single shared block/day availability hook exists across MILP, heuristics, playback, and rolling horizon; road-work timing is not a decision variable. | Kept enforcement at the tested `constraint-check` layer and documented the condition for future integration. |
| No real watershed or weather forecast. | The work is an operational exposure contract, not a hydrology model. | Used a synthetic reviewed hazard/asset fixture. |
| No asset condition or damage curve. | The phase records exposure context, not vulnerability economics. | Asset vulnerability class is descriptive only. |
| `main` advanced with the cuOpt memo during closeout. | Independent work merged while P16 was active. | Merged `origin/main` at `339d35b4`, reran the gates, and kept both changelog entries. |

## 6. Next phase

Recommended default: no immediate follow-on phase.

A later solver phase is justified only when:

- one shared block/day availability hook is honored by the MILP, SA, ILS, Tabu,
  playback, and rolling horizon;
- a reviewed hazard policy defines closure and warning enforcement;
- a reviewed road/culvert inventory and liability policy exist; and
- operations review confirms the constraint is meaningful.

Landscape-scale flood response remains in WS4/FEMIC, not FHOPS.

## 7. Decision

- [ ] Approve as written.
- [ ] Approve with the changes stated here: <changes>.
