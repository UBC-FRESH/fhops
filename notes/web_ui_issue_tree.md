# FHOPS Web UI Issue Tree

Date: 2026-10-24
Roadmap phase: P12 - FHOPS Web Application (WS4-Style)
Primary plan: `notes/web_ui_expansion_plan.md`
Reference implementation: `UBC-FRESH/ws4`, Phase 18 (#146) and
`notes/design/ws4-web-frontend.md`
Workflow contract: `AGENTS.md`; UBC-FRESH dev workflow issue standard

## Live GitHub structure

- Parent issue: [#171 - P12: FHOPS web application (WS4-style artefact reader)](https://github.com/UBC-FRESH/fhops/issues/171)
- Phase branch: `feature/p12-web-ui` (active from `main` at `52462d2`)
- Planning PR: #184 (draft)
- Status: active (2026-10-25); #178-#180 complete, #181 next

| Issue | Task | Child branch |
|---:|---|---|
| [#178](https://github.com/UBC-FRESH/fhops/issues/178) | P12.1 Service skeleton, run manifest, artefact discovery, and CLI entry — complete | `feature/p12-web-ui` |
| [#179](https://github.com/UBC-FRESH/fhops/issues/179) | P12.2 Read-only API, SPA shell, and skin loader — complete | `feature/p12-web-ui` |
| [#180](https://github.com/UBC-FRESH/fhops/issues/180) | P12.3 Map, layer tree, and day/period control — complete | `feature/p12-web-ui` |
| [#181](https://github.com/UBC-FRESH/fhops/issues/181) | P12.4 Schedule/Gantt, KPI, report, and comparison panels | `issue-181-web-panels` |
| [#182](https://github.com/UBC-FRESH/fhops/issues/182) | P12.5 Live runs, SSE, and run control | `issue-182-web-live` |
| [#183](https://github.com/UBC-FRESH/fhops/issues/183) | P12.6 Editable objective/locks, assistant, packaging, security, docs, and close-out | `issue-183-web-closeout` |

All six child issues are linked to parent #171 through GitHub sub-issues and assigned the `Task`
issue type. The parent carries the `Feature` issue type.

## Domain coverage

The UI is one application with three lenses: shift-level operational, Ghotb-derived log hauling,
and TOPM-style tactical-operational. A run manifest carries `domain` and `run_type`; the lens
selects the time control (day/shift vs period), layers, panels, KPIs, reports, and editable fields.
The issue bodies carry the domain-specific additions from the 2026-10-25 scope clarification.

## Dependencies

- P12.1 freezes the artefact contract and must land before the API or UI work.
- P12.2 (read-only API and shell) gates P12.3-P12.6.
- P12.3 and P12.4 can run in parallel once P12.2 is stable.
- P12.5 depends on P12.1's manifest/discovery and P12.2's run model.
- P12.6 depends on P12.2-P12.5.
- P11 hauling outputs are optional for the first cut: the UI names them as unavailable layers and
  follows the stable file contract from P11.5 when that phase lands.

## Activation checklist

- [x] Create `feature/p12-web-ui` from `main` at `52462d2`.
- [x] Update `ROADMAP.md` status from `queued` to `active` and record the activation date (`2026-10-25`).
- [x] Post an activation comment on #171.
- [x] Start #178 (complete).
- [ ] Re-read the WS4 design note and `ws4/web/app.py` before the first service line.

## Ongoing hygiene

- Update this table whenever a child issue starts, pauses, or closes.
- Do not close #171 until every child is closed, the phase PR is merged, and the maintainer approves
  the close-out report.
- Keep `ROADMAP.md`, `notes/web_ui_expansion_plan.md`, and `CHANGE_LOG.md` in sync with issue
  evidence.
