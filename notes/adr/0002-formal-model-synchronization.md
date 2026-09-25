# ADR 0002 — Formal Model Synchronization

Date: 2026-09-25
Status: Proposed for maintainer review
Parent issue: #56
Child issue: #57
Phase branch: `feature/phase5-formal-model-sync`
Child branch: `issue-57-phase-5.0-formulation-source-audit`

## Context

FHOPS now has two public optimization formulations that need durable mathematical documentation:

1. the original day×shift operational MILP in `fhops.model.milp.operational` and
   `fhops.model.milp.data`; and
2. the Phase 6 TOPM-inspired tactical–operational MILP in
   `fhops.model.milp.tactical_operational`.

The operational model already has a canonical Markdown source
(`docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md`) that generates TeX
and RST includes. The tactical model currently has a Sphinx how-to and API documentation, but no
canonical formulation source with equation-to-code traceability. `export_docs_assets.py` can render
Markdown/CSV primaries to `.tex` and `.rst`, but there is no dedicated drift check that fails when
generated outputs are stale.

## Decision

Use one canonical Markdown source per mathematical model under
`docs/softwarex/manuscript/sections/includes/`:

- `fhops_operational_formulation.md` for the operational MILP; and
- `fhops_tactical_operational_formulation.md` for the tactical–operational MILP.

Generated artifacts remain derived files:

- `<source>.tex` beside the Markdown source for LaTeX/manuscript use; and
- `docs/includes/softwarex/<source>.rst` for Sphinx inclusion.

`docs/softwarex/manuscript/scripts/export_docs_assets.py` remains the renderer. Phase 5.3 should add
a lightweight drift check that regenerates into a temporary directory and fails when checked-in
outputs differ from sources.

## Conventions

1. **Canonical math lives in Markdown.** Equations, variable/parameter definitions, objective
   profiles, and implementation mappings are edited only in the Markdown source.
2. **Generated outputs are not hand-edited.** TeX/RST files carry the existing auto-generated header.
3. **Traceability is mandatory.** Every equation block must name the corresponding Pyomo component,
   helper, or data-normalization function.
4. **Units are explicit.** Period, area, volume, cost, value, and discount-factor conventions are
   declared in the source.
5. **Provenance is documented.** The operational source continues to cite operational-model
   assumptions; the tactical source cites Oborn/TOPM lineage and Phase 6 implementation decisions.
6. **Manuscript inclusion is explicit.** Generating a TeX include does not force the current
   SoftwareX revision to include tactical math. Inclusion in a manuscript section remains an
   editorial decision; Sphinx and thesis-facing assets can consume the same source immediately.
7. **No semantic backporting.** If code and math disagree, Phase 5 documents the discrepancy and
   opens a child issue rather than silently rewriting solver behavior.

## Consequences

Positive:

- one source of truth for each model;
- manuscript, Sphinx, and thesis assets can be regenerated reproducibly;
- code review can detect mathematical drift;
- the new tactical formulation becomes citable without copying prose from docs.

Costs:

- generated artifacts add small diffs whenever math changes;
- every Pyomo component rename now requires a formulation-source update;
- the tactical formulation source adds one more document that must remain synchronized.

## Acceptance gates

This ADR is accepted when maintainers approve:

1. the two-source layout;
2. generated-artifact conventions;
3. the required equation-to-code mapping format;
4. the drift-check strategy assigned to #60; and
5. the decision that current SoftwareX text need not absorb tactical math until a future editorial
   change requests it.
