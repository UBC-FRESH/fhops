# Phase close-out report: P18 Hydrology documentation and reproducibility

Phase: P18 Hydrology documentation and reproducibility
Parent issue: #260
Pull request: to be opened
Evidence head: `fa83574d` (P18.4)
Date: 2026-10-28
Status: queued for approval. Not merged.

## Recommendation

Approve these actions. The agent carries them out in this order, and reads back
each result.

1. Treat the phase pull request as the single P18 pull request.
2. Squash-merge it into `main` and delete `feature/phase18-hydrology-docs`.
3. Close the P18.5 issue and parent issue #260 with closeout comments that cite
   the merge commit.
4. Keep the docs checker in CI. Do not claim a real watershed result or a
   solver-side hydrology capability.

Settings changes, each with its exact command. Each one runs only after its own
approval.

- None.

## 1. Objectives and acceptance

| Criterion | Evidence | Status |
| --- | --- | --- |
| The audit names every missing workflow and its owner. | `notes/p18_hydrology_docs_audit.md`; P18.1; PR #266. | Met |
| The quickstart pins versions, commands, fixtures, and expected outputs. | `docs/howto/hydrology_quickstart.rst`; generator; P18.2; PR #269. | Met |
| The contract index covers producer, landscape, and operational schemas. | `docs/reference/hydrology_contract_index.rst`; P18.3; PR #270. | Met |
| Executable docs checks run in CI. | `scripts/check_hydrology_docs.py`; P18.4; PR #272. | Met |
| The WS4 path is reproducible. | Generator + manual WS4 run: preflight ready, 2 rows, 0 refusals. | Met with the stated CI limit |
| The FHOPS path is reproducible. | Generator test and docs checker run the FHOPS CLI path. | Met |
| Synthetic contract demonstrations are not real watershed results. | Quickstart, contract index, audit, and this report. | Met |
| FHOPS quality suite, docs build, and docs checker are green. | Section 3. | Met |

## 2. Workflow compliance

- Parent issue #260 existed before the Phase 18 branch.
- Phase branch: `feature/phase18-hydrology-docs`.
- Child issues #261-#265 are linked as sub-issues. #261-#264 are merged and
  closed; #265 is this closeout.
- Child PRs: #266 (audit), #269 (quickstart), #270 (contract index), #272
  (docs checks).
- The phase note is `notes/phase18_hydrology_docs_reproducibility.md`.
- Roadmap, changelog, docs, and issue bodies were kept in step.
- P17 is the active tree-scale phase; P18 is the documentation phase. The
  numbering collision is recorded.
- One final phase pull request carries the branch into `main`.
- No tag, release, visibility, or settings change is included.

## 3. Gate evidence

Local gates on the closeout branch:

- Full `pytest -q`: exit 0.
- `python scripts/check_hydrology_docs.py --check-external`: OK.
- `ruff format --check src tests`: clean.
- `ruff check src tests`: clean.
- `mypy src`: clean.
- `pre-commit run --all-files`: passed.
- `sphinx-build -b html docs _build/html -W`: succeeded.

Child CI runs:

| Task | PR | CI run | Result |
| --- | --- | --- | --- |
| P18.1 | #266 | 40591804033 | green |
| P18.2 | #269 | 40596545533 | green |
| P18.3 | #270 | 40599793897 | green |
| P18.4 | #272 | 40604138455 | green |

The P18.2 WS4 path was additionally run manually in the workspace:
`preflight_screening_ready=true`, `rows=2`, `refusals=0`.

## 4. CI evidence

| Run ID | Head commit | Conclusion | Notes |
| --- | --- | --- | --- |
| pending | closeout commit | not yet run | The final phase PR runs CI after the report commit. |

## 5. Deviations

| Deviation | Cause | Remedy |
| --- | --- | --- |
| Phase number is P18, not P17. | P17 is the active tree-scale inventory phase. | Recorded the mapping; P17 was not renumbered. |
| WS4 CLI is not run in FHOPS CI. | FHOPS CI does not install WS4. | The generator creates the WS4 workspace and the WS4 path is manually verified; the checker runs the FHOPS path and file checks. |
| No real watershed result. | Chapman is data-blocked; Seymour has no reviewed bundle. | Synthetic quickstart only; data/review blockers remain. |
| No solver-side hydrology. | P16 decision kept enforcement at the constraint-check layer. | Documented in the contract index and quickstart. |

## 6. Next phase

Recommended default: no immediate docs phase.

Remaining work is data/review, not documentation:

- current or governed gauge series;
- reviewed DEM vertical metadata and coverage;
- reviewed receptor geometry and capacity;
- reviewed crosswalk and culvert inventory;
- hydrologist review;
- a real watershed pilot.

The docs checker and quickstart should be updated when those inputs exist.

## 7. Decision

- [ ] Approve as written.
- [ ] Approve with the changes stated here: <changes>.
