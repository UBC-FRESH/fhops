# SoftwareX Reference Vault

Captured artifacts that anchor the FHOPS manuscript plan. Everything here is snapshotted for offline use so we can track exactly which instructions/templates informed each drafting cycle.

| Artifact | Path | Source URL | Retrieved | Notes |
|----------|------|------------|-----------|-------|
| Guide for Authors (HTML snapshot) | `softwarex_guide_for_authors.html` | https://www.elsevier.com/journals/softwarex/2352-7110/guide-for-authors | 2025-11-23 | Pulled via `curl -L`; contains the live instructions including metadata tables, highlights requirements, and submission checklist. |
| Elsevier LaTeX Template (elsarticle) | `templates/elsarticle-template.zip` | https://www.elsevier.com/__data/assets/file/0011/56846/elsarticle-template.zip | 2025-11-23 | Official `elsarticle` bundle (class files, sample manuscript, reference styles). Use this as the base for `docs/softwarex/manuscript/`. |
| Most-cited SoftwareX list | `softwarex_top_cited_crossref.json` | https://api.crossref.org/journals/2352-7110/works?sort=is-referenced-by-count&order=desc&rows=25 | 2025-11-23 | Crossref API dump used to seed the exemplar shortlist. Column `is-referenced-by-count` gives citation counts. |
| Exemplar PDFs + metadata | `examples/<slug>/` | Individual ScienceDirect DOIs (see per-folder metadata) | 2025-11-23 | Nine high-quality SoftwareX papers (PyLESA, pycity_scheduling, cashocs, PyDDRBG, GROMACS, libxc, MOOSE, TSFEL, Advanced LIGO/Virgo open data). Each folder stores `metadata.md`, the PDF, and any future annotations. |

> Update cadence: whenever Elsevier revises instructions or templates, add the new snapshot here with a new row (include date). Keep prior versions for traceability; do **not** overwrite without note.
