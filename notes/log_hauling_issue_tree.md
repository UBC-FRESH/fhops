# Log Hauling Issue Tree

Date: 2026-10-24
Roadmap phase: P11 - Log Hauling and Mill Delivery Optimization (Ghotb-Inspired)
Primary plan: `notes/log_hauling_expansion_plan.md`
Workflow contract: `AGENTS.md`; UBC-FRESH dev workflow issue standard

## Live GitHub structure

- Parent issue: [#170 - P11: Log hauling and mill delivery optimization (Ghotb decomposition)](https://github.com/UBC-FRESH/fhops/issues/170)
- Phase branch: `feature/p11-log-hauling` (reserved; created from `main` at activation)
- Planning PR: #184 (draft)
- Status: close-out queued (2026-10-25); #172-#177 complete; PR #185 awaits approval

| Issue | Task | Child branch |
|---:|---|---|
| [#172](https://github.com/UBC-FRESH/fhops/issues/172) | P11.1 Provenance, contract, and formulation audit — complete | `feature/p11-log-hauling` |
| [#173](https://github.com/UBC-FRESH/fhops/issues/173) | P11.2 Phase I monthly flow MILP and goal programming — complete | `feature/p11-log-hauling` |
| [#174](https://github.com/UBC-FRESH/fhops/issues/174) | P11.3 Phase II daily routing and scheduling MILP — complete | `feature/p11-log-hauling` |
| [#175](https://github.com/UBC-FRESH/fhops/issues/175) | P11.4 SA solution approach, SPT decoder, and calibration — complete | `feature/p11-log-hauling` |
| [#176](https://github.com/UBC-FRESH/fhops/issues/176) | P11.5 FHOPS integration, CLI, reporting, and example case — complete | `feature/p11-log-hauling` |
| [#177](https://github.com/UBC-FRESH/fhops/issues/177) | P11.6 Validation, documentation, formulation sync, and close-out — complete | `feature/p11-log-hauling` |
| [#187](https://github.com/UBC-FRESH/fhops/issues/187) | P11.7 Marine/barge haul legs (explicit water mode, barges, ports, water arcs, barge scheduling) — implementation | `issue-187-marine-haul` |

All six child issues are linked to parent #170 through GitHub sub-issues and assigned the `Task`
issue type. The parent carries the `Feature` issue type. The repository did not previously carry
`phase`/`task` labels; both were added for this queue and future phases.

## Progress

- 2026-10-25: #172 complete. The `hauling:` contract, schema 1.1.0 guard, loader support, example,
  docs, and formulation audit are on `feature/p11-log-hauling`.
- 2026-10-25: #173 complete. Phase I cost/workload/goal models, result payloads, summary printer,
  and the example solve are on the phase branch.
- 2026-10-25: #174 complete. Phase II continuous-time scheduling, loader assignment/order, MTZ
  routing, simulator/validator, and the example day-1 schedule are on the phase branch.
- 2026-10-25: #175 complete. Route-permutation SA, SPT decoder, operators, calibration/benchmark
  script, and MIP parity (2992.50) are on the phase branch.
- 2026-10-25: #176 complete. Operational/tactical bridges, `fhops haul` CLI, stable artefact
  writers, Markdown report, and the generated scale case are on the phase branch.
- 2026-10-25: #177 complete. Parity/scale evidence, canonical formulation assets, docs, and the
  close-out report are on the phase branch. PR #185 is queued for approval.
- 2026-10-25: #187 marine/barge extension implemented on `issue-187-marine-haul`: contract,
  Phase I marine flow, barge-cycle scheduler, CLI artefacts, docs, and the Sunshine Coast →
  Howe Sound fixture. PR #195 opened against `main`.

## Post-P11 follow-up: multi-day marine cycles

- Parent phase: [#197](https://github.com/UBC-FRESH/fhops/issues/197) (Phase 13)
- Child task: [#196](https://github.com/UBC-FRESH/fhops/issues/196) (P13.1)
- Branch: `feature/phase13-multiday-marine`
- Design: `notes/multiday_marine_cycles.md`
- Regression fixture: `examples/hauling_marine_multiday/`
- Status: design and failing regression fixture complete; solver change queued for P13.2.

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
