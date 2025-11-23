# SoftwareX Manuscript Outline (Draft 0)

This mirrors the canonical SoftwareX structure. Each section lists:
1. **Purpose** – why the section exists per author instructions.
2. **FHOPS source material** – where we will pull content from (code, docs, benchmarks, etc.).
3. **Status** – TBD / Drafting / Ready.

| Section | Purpose | FHOPS Source Material | Status |
|---------|---------|-----------------------|--------|
| Title + Highlights | Crisp positioning + 3 bullet highlights emphasising novelty. | FHOPS mission statement, differentiators from roadmap. | TBD |
| `Code metadata` table | Provide repo link, license, dependencies, build commands, support email. | `README.md`, `pyproject.toml`, ops team contact, release cadence. | TBD |
| `Current code version` table | Document version info + OS/dep matrix. | Release notes (`CHANGE_LOG.md`), CI matrix. | TBD |
| Abstract | ≤200 words: problem, solution, results, impact. | To be synthesized from final sections. | TBD |
| 1. Motivation and significance | Explain FHOPS niche, gaps in existing tools, target users. | FHOPS_ROADMAP, thesis alignment plan, exemplar quotes (PyLESA gap analysis). | TBD |
| 2. Software description | Architecture, components, workflow, dependencies. | `src/` modules, architecture diagrams (assets). | TBD |
| 3. Illustrative example | Concrete use-case / benchmark showing FHOPS in action. | Bench scripts (`benchmarks/`), evaluation notebooks, synthetic fleet run. | TBD |
| 4. Impact | Adoption metrics, community, downstream projects, API stability. | Download stats, pilot logos, libxc/MOOSE style governance summary. | TBD |
| 5. Conclusions (and future work) | Summarize benefits + roadmap. | FHOPS roadmap, release plan. | TBD |
| CRediT statement | Author contributions. | TBD once author list finalised. | TBD |
| Acknowledgements / Funding | Include grant + institutional support. | FHOPS sponsor info. | TBD |
| References | BibTeX file synced with Sphinx + README. | `manuscript/references.bib` (planned). | TBD |
| Appendix / Supplementary (if needed) | Extra tables, dataset descriptions. | CLI output, telemetry tables. | TBD |

## Cross-linking with Sphinx
- Shared narrative blocks (Overview, architecture descriptions) should live in `sections/includes/` so both the LaTeX manuscript and the Sphinx docs can reuse them.
- Figures/tables: generate sources into `docs/softwarex/assets/figures` and reference them from both outputs to avoid divergence.

## Next content tasks
1. Extract canonical section requirements from the Guide for Authors and drop them inline (quotes or footnotes) to keep us honest.
2. Assign DRIs for each section (align with FHOPS team workloads).
3. Draft the Highlights + Abstract last, after sections stabilize.
