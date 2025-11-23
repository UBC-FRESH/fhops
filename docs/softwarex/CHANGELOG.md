# SoftwareX Manuscript Sub-project Change Log

Only changes that affect the SoftwareX planning/manuscript workspace are recorded here. Core FHOPS code/documentation changes still belong in the repository-wide `CHANGE_LOG.md`.

## 2025-11-23 — Workspace scaffolding & exemplar analysis
- Created the `docs/softwarex/` workspace with dedicated `reference/`, `manuscript/`, `assets/`, and `submissions/` folders plus a top-level README describing ownership and next steps.
- Logged provenance for all reference artifacts (Guide for Authors snapshot, elsarticle template bundle, Crossref most-cited dump, nine exemplar PDFs) via `docs/softwarex/reference/README.md`.
- Seeded the manuscript working area: added `manuscript/README.md` outlining the build workflow and `manuscript/outline.md` mirroring the SoftwareX section structure with FHOPS source notes.
- Expanded `notes/softwarex_exemplar_analysis.md` with takeaways + citation-ready cues for all nine exemplar papers to guide drafting and readiness criteria.
- Downloaded the CTAN `elsarticle` template, extracted it into `docs/softwarex/manuscript/elsarticle/`, and updated the manuscript README to record the template snapshot plus next actions.
- Added an initial `fhops-softx.tex` wrapper and a `Makefile` that runs `latexmk -pdf` into `build/`, establishing the traditional TeX Live toolchain for future drafts.
