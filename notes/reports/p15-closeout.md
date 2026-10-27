# Phase close-out report: P15 Consume FEMIC hydrology response bundles

Phase: P15 Consume FEMIC hydrology response bundles
Parent issue: #218
Pull request: to be opened
Evidence head: `ee33794f` (P15.6 plus the `origin/main` 1.1.0 merge)
Date: 2026-10-27
Status: queued for approval. Not merged.

## Recommendation

Approve these actions. The agent carries them out in this order, and reads back
each result.

1. Treat the phase pull request as the single P15 pull request.
2. Squash-merge it into `main` and delete `feature/phase15-hydrology-consumer`.
3. Close the P15.6 issue and parent issue #218 with closeout comments that cite
   the merge commit.
4. Do not start a real watershed pilot. Keep optimizer-integrated exposure
   deferred until a reviewed bundle, receptor evidence, and a schedule-derived
   road-state contract exist.

Settings changes, each with its exact command. Each one runs only after its own
approval.

- None.

## 1. Objectives and acceptance

| Criterion | Evidence | Status |
| --- | --- | --- |
| FHOPS validates and pins a FEMIC hydrology bundle with per-artifact checksums. | `fhops.scenario.hydrology`; `tests/scenario/test_hydrology_contract.py`; PR #225. | Met |
| A validated bundle is registered in a scenario without copying it. | `Scenario.hydrology_products`; `fhops scenario hydrology register`; tests; PR #227. | Met |
| Every in-scope block, landing, and road maps explicitly or records a gap. | `fhops.scenario.hydrology_mapping`; `tests/scenario/test_hydrology_mapping.py`; PR #229. | Met |
| Exposure is explicit, reviewed, and bound to one assignments CSV. | `fhops.scenario.hydrology_exposure`; `fhops scenario hydrology exposure`; PR #230. | Met |
| One schedule produces per-watershed/receptor/period rows and refusals. | `fhops.scenario.hydrology_screen`; `tests/scenario/test_hydrology_screen.py`; PR #231. | Met |
| Readiness policies gate screening, including reviewed mapping/exposure. | `enforce_hydrology_readiness`; policy tests. | Met |
| The end-to-end CLI path is proven on a synthetic fixture. | `tests/scenario/test_hydrology_integration.py`. | Met |
| No real watershed, flood map, or regulatory result is claimed. | This report, docs, screen caveats, and issue bodies. | Met |
| FHOPS quality suite and docs build are green. | Section 3. | Met |

## 2. Workflow compliance

- Parent issue #218 existed before the Phase 15 branch.
- Phase branch: `feature/phase15-hydrology-consumer`.
- Child issues #219-#224 are linked as sub-issues. #219-#223 are merged and
  closed; #224 is this closeout.
- Child PRs: #225, #227, #229, #230, #231. #230 included a maintainer follow-up
  adding CLI exposure validation and digest preservation. #231 included a
  maintainer hardening commit for provenance and validation.
- Commit messages use P15 task prefixes where applicable.
- Roadmap, the authoritative note, changelog, and issue bodies were kept in
  step.
- One final phase pull request carries the phase branch into `main`.
- No tag, release, visibility, or settings change is included.

## 3. Gate evidence

Local gates on the phase branch:

- Full `pytest -q`: exit 0.
- `ruff format --check src tests`: clean.
- `ruff check src tests`: clean.
- `mypy src`: clean.
- `pre-commit run --all-files`: passed.
- `sphinx-build -b html docs _build/html -W`: succeeded.

Child CI runs:

| Task | PR | CI run | Result |
| --- | --- | --- | --- |
| P15.1 | #225 | 40422350901 | green |
| P15.2 | #227 | 40455408808 | green |
| P15.3 | #229 | 40460134892 | green |
| P15.4 | #230 | 40464595183 | green |
| P15.5 | #231 | 40472960655 | green |

## 4. CI evidence

| Run ID | Head commit | Conclusion | Notes |
| --- | --- | --- | --- |
| pending | closeout commit | not yet run | The final phase PR runs CI after the report commit. |

## 5. Deviations

| Deviation | Cause | Remedy |
| --- | --- | --- |
| No real watershed screen. | Chapman is data-blocked and Seymour has no reviewed bundle. | Used synthetic/public fixture data only; documented the data preconditions. |
| Optimizer-integrated exposure is not implemented. | A fixed table bound to one schedule cannot represent every solver candidate. | The screen is one-schedule only; the optimizer remains disconnected and the follow-up is in the roadmap backlog. |
| P15.4 CLI validation and digest preservation were added by a maintainer follow-up. | The initial child branch stopped at the loader. | Accepted the follow-up and verified the expanded tests. |
| P15.5 provenance/validation hardening was added by a maintainer follow-up. | The initial child branch had a narrower screen. | Accepted the hardening commit and verified the expanded tests. |
| `main` advanced to FHOPS 1.1.0 during closeout. | Release work merged while P15 was active. | Merge `origin/main` into the phase branch, rerun the gates, and record the merge. |

## 6. Next phase

Recommended default: no immediate hydrology phase.

The next hydrology step is optimizer-integrated exposure, and it needs:

- a reviewed FEMIC bundle and receptor evidence for a real watershed;
- a road-state contract that exposes built, used, decommissioned, and culvert
  exposure per candidate schedule;
- a reviewed response surface that uses those features; and
- hydrologist review before operational claims.

Until then, the one-schedule consumer is the supported surface.

## 7. Decision

- [ ] Approve as written.
- [ ] Approve with the changes stated here: <changes>.
