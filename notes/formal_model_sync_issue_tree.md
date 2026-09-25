# Formal Model Synchronization Issue Tree

Date: 2026-09-25
Roadmap phase: Phase 5 — Formal Model Documentation Synchronization
Primary notes: `notes/mip_formulation_plan.md`, `docs/softwarex/manuscript/sections/includes/README.md`
Workflow contract: `AGENTS.md` → “Roadmap phase and issue-tree workflow”

## Live GitHub structure

- Parent issue: [#56 — Phase 5: Formal Model Documentation Synchronization](https://github.com/UBC-FRESH/fhops/issues/56)
- Phase branch: `feature/phase5-formal-model-sync`

| Issue | Task | Child branch |
|---:|---|---|
| [#57](https://github.com/UBC-FRESH/fhops/issues/57) | Phase 5.0 — canonical formulation source audit and ADR | `issue-57-phase-5.0-formulation-source-audit` |
| [#58](https://github.com/UBC-FRESH/fhops/issues/58) | Phase 5.1 — operational MILP traceability and regeneration checks | `issue-58-phase-5.1-operational-traceability` |
| [#59](https://github.com/UBC-FRESH/fhops/issues/59) | Phase 5.2 — tactical–operational MILP canonical formulation | `issue-59-phase-5.2-tactical-formulation` |
| [#60](https://github.com/UBC-FRESH/fhops/issues/60) | Phase 5.3 — formulation drift checks and documentation closeout | `issue-60-phase-5.3-formulation-drift-closeout` |

All four child issues are linked to parent #56 through GitHub sub-issues and assigned the
repository `Feature` issue type.

## Scope note

Phase 5 originally targeted the operational MILP only. Following Phase 6, the phase now covers both
the day×shift operational MILP and the TOPM-inspired tactical–operational MILP. The goal is one
canonical mathematical source per model, synchronized manuscript/Sphinx outputs, and drift checks
that catch equation-to-code divergence.

## Ongoing hygiene

- Update this table whenever a child issue starts, pauses, or closes.
- Do not close parent #56 until every child issue is closed and maintainers approve Phase 5.
- Keep `ROADMAP.md`, `notes/mip_formulation_plan.md`, the SoftwareX include README, and
  `CHANGE_LOG.md` synchronized with issue evidence.
