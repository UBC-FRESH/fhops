# SoftwareX Manuscript Snippets in Sphinx

This directory stores the ReStructuredText outputs that mirror the SoftwareX manuscript
snippets. Each file is auto-generated from the Markdown/CSV primaries under
`docs/softwarex/manuscript/sections/includes/` by running:

```bash
python docs/softwarex/manuscript/scripts/export_docs_assets.py
# or: make assets  # which invokes the exporter plus the rest of the asset pipeline
```

## Usage

- Reference any snippet via ``.. include:: includes/softwarex/<name>.rst`` inside the
  Sphinx docs (see `docs/overview.rst` for the motivation narrative and PRISMA workflow).
- Figures generated from the same pipeline (for example,
  `docs/softwarex/assets/figures/prisma_overview.png`) can be embedded with the standard
  ``.. figure::`` directive so the documentation and manuscript share identical visuals.
- Do **not** edit the `.rst` files directly; make changes to the Markdown/CSV sources and
  rerun the exporter.

## Regeneration checklist

1. Update the Markdown/CSV files in `sections/includes/`.
2. Run the exporter (direct invocation or via `make assets`); confirm the console log
   lists the regenerated `.tex` and `.rst` files.
3. Rebuild the docs/manuscript to verify formatting parity.

This workflow satisfies the Phase 2 requirement to keep manuscript snippets modular and
reused verbatim inside the Sphinx user guide.
