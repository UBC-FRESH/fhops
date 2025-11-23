# Supplementary Package Scaffold

SoftwareX submissions can include optional supplementary material (datasets, extended tables, scripts). This directory holds:

- `supplementary_template.tex` – LaTeX wrapper for any supplementary PDF material.
- `data/` – placeholder for derived CSV/JSON assets referenced only in the supplement.
- `figures/` – placeholder for high-resolution figures not embedded in the main article.

Keep this folder reproducible: every artifact here must trace back to a script inside `docs/softwarex/manuscript/scripts/` (invoked via `make assets`).
