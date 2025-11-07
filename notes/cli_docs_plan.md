# CLI & Documentation Plan

Date: 2025-??-??
Status: Draft — governs user-facing narrative and tooling upgrades.

## Objectives
- Deliver comprehensive Sphinx documentation (overview, tutorials, API, CLI reference).
- Ensure CLI ergonomics support discoverability (rich help, examples, presets).
- Align documentation publishing with Read the Docs automation.

## Tasks
- [ ] Inventory current CLI commands and options; identify missing help text or examples.
- [ ] Scaffold Sphinx sections (overview, how-to guides, API reference, CLI reference).
- [ ] Integrate `sphinx-click` (or equivalent) for automatic CLI docs generation.
- [ ] Prepare RTD configuration and badges; test build locally before enabling remote builds.

## Documentation Deliverables
- [ ] Tutorials: quickstart, solver comparison, evaluation workflows.
- [ ] API modules documented via autodoc/autosummary.
- [ ] CLI reference with command usage and sample invocations.
- [ ] Contribution guide updates referencing planning artefacts.

## Open Questions
- Should we host examples as Jupyter notebooks alongside rendered HTML via nbsphinx?
- How to version documentation in sync with releases vs development snapshots?
