# Phase close-out report: P13 Multi-day marine barge cycles

Phase: P13 Multi-day marine barge cycles
Parent issue: #197
Pull request: #200, `issue-199-multiday-model` into `main`
Evidence head: `e570fddb`, the head that the gates and CI run below cover
Report commit: the commit that adds this report. Its CI run is posted on the pull request.
Date: 2026-10-25
Status: queued for approval. Not merged.

## Recommendation

Approve these actions:

1. Squash-merge pull request #200, and delete the branch `issue-199-multiday-model`.
2. Close task #199 and parent #197 with a closeout comment that cites the merge commit.
3. Keep the same-day marine fixture and the new multi-day fixture as the regression pair.
4. Do not create a release, tag, or sustainable label from P13.
5. Keep current terminal/vessel/rate data and the GNN published transport switch as separate work.

Settings changes, each with its exact command. Each one runs only after its own approval.

- None.

## 1. Objectives and acceptance

| Criterion | Evidence | Status |
| --- | --- | --- |
| Design note and failing regression fixture. | P13.1, merged `65b0d2b1`; `notes/multiday_marine_cycles.md`; `examples/hauling_marine_multiday/`. | met |
| Multi-day departure/arrival timing. | P13.2; `MarineLane.arrival_lag_days`; Quatsino -> Ladysmith departure day 1, arrival day 5. | met |
| In-transit/destination timing. | Destination port inventory and yard delivery occur on arrival day; demand-before-arrival is infeasible. | met |
| Multi-day barge occupancy. | Sliding window; 3,955-minute cycle, eight-day occupancy, one barge, one trip. | met |
| Same-day marine behaviour unchanged. | All existing `tests/hauling` pass; Sunshine Coast -> Howe Sound fixture unchanged. | met |
| Reporting. | `marine_flows` and `barge_trips` carry arrival/transit/occupancy fields; output schema `1.1.0`. | met |
| Gates. | ruff, mypy, full pytest, pre-commit, Sphinx, CI. | met |

## 2. Workflow compliance

- Parent issue before work: #197 created before P13.1/P13.2 branches.
- P13.1: #196, branch `issue-196-multiday-marine`, merged `65b0d2b1` (PR #198).
- P13.2: #199, branch `issue-199-multiday-model`, PR #200.
- Commit messages start with task IDs: `cb617525` (P13.1), `e570fddb` (P13.2).
- Roadmap, issue tree, design note, docs, and changelog updated.
- Approval gates: issue and branch creation only; no settings, tag, release, or visibility change.

## 3. Gate evidence

`e570fddb`:

- `ruff format src tests`: clean.
- `ruff check src tests`: clean.
- `mypy src`: clean.
- Full `pytest`: passed.
- `pre-commit run --all-files`: passed.
- `sphinx-build -b html docs _build/html -W`: build succeeded.
- `fhops haul validate|plan examples/hauling_marine_multiday/scenario.yaml`: optimal, 62,771.667 CAD.

## 4. CI evidence

| Run ID | Head commit | Conclusion | Notes |
| --- | --- | --- | --- |
| `40237995538` | `e570fddb` | success | lint-test-docs passed. |

## 5. Deviations

| Deviation | Cause | Remedy |
| --- | --- | --- |
| Delivery is fixed to the cargo-arrival day. | The first model does not yet carry port storage past arrival. | Documented as a limit; a later task can add a delivery-lag variable. |
| Trips that would finish after the horizon are disallowed. | No initial/terminal in-transit state is modeled. | Documented; the fixture and cutoff handle the current case. |
| Non-integer voyage durations are rounded up to whole days. | Phase I is a daily model. | Documented; this is conservative for capacity. |
| No current carrier or terminal rates. | Public data is unavailable. | Kept the proxy/assumption boundary separate. |

## 6. Next phase

No phase is activated by this report. The next work is data and integration:

- current terminal, vessel, road/water, and carrier/terminal data;
- a GNN-specific solved scenario using those inputs;
- a decision on whether to switch the published GNN transport base.

The existing GNN proxy is diagnostic and remains separate.

## 7. Decision

- [ ] Approve as written.
- [ ] Approve with the changes stated here: <changes>.
