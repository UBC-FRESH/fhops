# Formal Model Synchronization Audit

Date: 2026-09-25
Issue: #57
Parent: #56

## Current assets

| Asset | Current role | Status | Follow-up |
|---|---|---|---|
| `docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md` | Canonical operational MILP Markdown source | Present; used to generate TeX/RST | #58 refreshes traceability and regeneration checks |
| `docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.tex` | Manuscript include generated from Markdown | Present; auto-generated | Keep generated only |
| `docs/includes/softwarex/fhops_operational_formulation.rst` | Sphinx include generated from Markdown | Present; auto-generated | Keep generated only |
| `docs/howto/optimization_formulation.rst` | Sphinx wrapper for operational formulation | Present | #58 keeps it synchronized |
| `src/fhops/model/milp/operational.py` | Operational Pyomo model | Active implementation | #58 audits equation mapping |
| `src/fhops/model/milp/data.py` | Operational bundle normalization | Active implementation | #58 audits parameter mapping |
| `src/fhops/model/milp/tactical_operational.py` | Tactical–operational Pyomo model | Active implementation from Phase 6 | #59 adds canonical formulation source |
| `docs/howto/tactical_operational.rst` | Tactical planning how-to with abbreviated equations | Present, but not the canonical full formulation | #59 links to generated canonical include |
| `docs/softwarex/manuscript/scripts/export_docs_assets.py` | Markdown/CSV → TeX/RST renderer | Present | #60 adds/regresses drift checking |
| `docs/softwarex/manuscript/sections/includes/README.md` | Shared include mapping | Present | #57 records Phase 5 issue mapping |

## Gaps

1. There is no canonical tactical–operational formulation source equivalent to the operational
   Markdown include.
2. The operational traceability table exists but has not been rechecked since the operational model
   evolved.
3. `export_docs_assets.py` regenerates outputs but does not currently fail on source/output drift.
4. The SoftwareX include README still frames formulation sync as operational-only.
5. The manuscript may not need the tactical formulation for the current SoftwareX revision; the
   canonical TeX include should still exist so thesis and future manuscripts do not fork math.

## 2026-09-25 progress

- #57 established the canonical source/ADR layout.
- #58 converted the operational implementation mapping into an explicit equation/component/data
  provenance table and added `tests/test_operational_formulation_traceability.py` to verify that
  every mapped Pyomo component exists in both the formulation and implementation.
- The shared exporter regenerated the operational TeX/RST includes cleanly after the table update.
- #59 adds `fhops_tactical_operational_formulation.md` as the canonical TOPM-inspired tactical
  source, generates TeX/RST includes, links the tactical how-to, and adds static traceability tests.

## Decisions needed

- Confirm canonical source location and naming for the tactical formulation.
- Confirm that generated `.tex`/`.rst` files are checked in but never edited directly.
- Confirm the drift-check command and expected local/CI placement.
- Confirm whether SoftwareX manuscript inclusion of tactical math is deferred to a future revision
  while Sphinx/thesis assets consume the same source immediately.
