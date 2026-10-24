# Log Hauling Issue Tree

Date: 2026-10-24
Roadmap phase: P11 - Log Hauling and Mill Delivery Optimization (Ghotb-Inspired)
Primary plan: `notes/log_hauling_expansion_plan.md`
Workflow contract: `AGENTS.md`; UBC-FRESH dev workflow issue standard

## Live GitHub structure

- Parent issue: [#170 - P11: Log hauling and mill delivery optimization (Ghotb decomposition)](https://github.com/UBC-FRESH/fhops/issues/170)
- Phase branch: `feature/p11-log-hauling` (reserved; created from `main` at activation)
- Status: queued

| Issue | Task | Child branch |
|---:|---|---|
| [#172](https://github.com/UBC-FRESH/fhops/issues/172) | P11.1 Provenance, contract, and formulation audit | `issue-172-hauling-contract` |
| [#173](https://github.com/UBC-FRESH/fhops/issues/173) | P11.2 Phase I monthly flow MILP and goal programming | `issue-173-hauling-flow` |
| [#174](https://github.com/UBC-FRESH/fhops/issues/174) | P11.3 Phase II daily routing and scheduling MILP | `issue-174-hauling-schedule` |
| [#175](https://github.com/UBC-FRESH/fhops/issues/175) | P11.4 SA solution approach, SPT decoder, and calibration | `issue-175-hauling-sa` |
| [#176](https://github.com/UBC-FRESH/fhops/issues/176) | P11.5 FHOPS integration, CLI, reporting, and example case | `issue-176-hauling-integration` |
| [#177](https://github.com/UBC-FRESH/fhops/issues/177) | P11.6 Validation, documentation, formulation sync, and close-out | `issue-177-hauling-closeout` |

All six child issues are linked to parent #170 through GitHub sub-issues and assigned the `Task`
issue type. The parent carries the `Feature` issue type. The repository did not previously carry
`phase`/`task` labels; both were added for this queue and future phases.

## Activation checklist

- [ ] Create `feature/p11-log-hauling` from the then-current `main`.
- [ ] Create child branches from the phase branch only when isolated review is needed.
- [ ] Update `ROADMAP.md` status from `queued` to `active` and record the activation date.
- [ ] Post an activation comment on #170.
- [ ] Start #172; it gates every other child.

## Ongoing hygiene

- Update this table whenever a child issue starts, pauses, or closes.
- Do not close #170 until every child is closed, the phase PR is merged, and the maintainer approves
  the close-out report.
- Keep `ROADMAP.md`, `notes/log_hauling_expansion_plan.md`, and `CHANGE_LOG.md` in sync with issue
  evidence.
