# CLI & Documentation Plan

Date: 2025-??-??
Status: Draft — governs user-facing narrative and tooling upgrades.

## Objectives
- Deliver comprehensive Sphinx documentation (overview, tutorials, API, CLI reference).
- Ensure CLI ergonomics support discoverability (rich help, examples, presets).
- Document mobilisation, harvest systems, and shift scheduling capabilities as they land.
- Align documentation publishing with Read the Docs automation and thesis alignment notes.

## Tasks
- [x] Inventory current CLI commands and options; identify missing help text or examples. *(Covered in CLI reference quick pass; baseline usage documented.)*
- [x] Scaffold Sphinx sections (overview, how-to guides, API reference, CLI reference).
- [ ] Add documentation for modular structure (`notes/modular_reorg_plan.md`) and new feature areas (mobilisation, systems, synthetic datasets).
- [ ] Integrate `sphinx-click` (or equivalent) for automatic CLI docs generation.
- [ ] Prepare RTD configuration and badges; test build locally before enabling remote builds.

## Documentation Deliverables
- [x] Tutorials: quickstart, solver comparison, evaluation workflows. *(Quickstart expanded with tiny7 + regression baseline; solver comparison/evaluation remain to-do but tracked in roadmap.)*
- [ ] API modules documented via autodoc/autosummary.
- [ ] CLI reference with command usage and sample invocations.
- [ ] Contribution guide updates referencing planning artefacts.

## Shift-Aware Documentation Punch List — 2025-11-09
1. **CLI Reference**
   - Expand `fhops solve-*` sections with examples showing multi-shift calendars (`--shift-profile`, `--timeline-file`), mobilisation interactions, and troubleshooting tips when shift IDs are missing.
   - Document the forthcoming shift-aware playback exports (`fhops eval playback --shift-out`) and benchmark harness metrics.
2. **How-to Guides**
   - Update `docs/howto/quickstart.rst` and `docs/howto/data_contract.rst` with step-by-step instructions for defining shifts, including YAML snippets and fixture references.
   - Add a short “Shift Schedules” how-to (or extend mobilisation guide) explaining blackout windows, night shifts, and their solver implications.
3. **Release Notes & CHANGE_LOG hooks**
   - Reserve a section in CHANGE_LOG entries once shift support lands so downstream users can track migration requirements.
4. **Validation Aids**
   - Provide sample CLI commands + expected outputs for shift-enabled scenarios to aid manual validation (e.g., comparing day vs shift KPI totals).

## Open Questions
- Should we host examples as Jupyter notebooks alongside rendered HTML via nbsphinx?
- How to version documentation in sync with releases vs development snapshots?
