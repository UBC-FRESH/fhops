# SoftwareX Manuscript Outline (Draft 0)

This mirrors the canonical SoftwareX structure. Each section lists:
1. **Purpose** – why the section exists per author instructions.
2. **FHOPS source material** – where we will pull content from (code, docs, benchmarks, etc.).
3. **Status** – TBD / Drafting / Ready.

| Section | Guide requirement (per SoftwareX) | FHOPS source material | Sphinx reuse? | Status |
|---------|-----------------------------------|-----------------------|--------------|--------|
| Title + Highlights | Title must emphasise software purpose; Highlights (3 bullets, ≤85 chars) must capture capability, availability, validation. | FHOPS mission statement, differentiators from FHOPS_ROADMAP, release cadence notes. | Overview landing page + release notes (shared highlight text). | Planning |
| Code metadata table | Mandatory table itemising repo URL, license, OS support, dependencies, doc link, contact. | `README.md`, `pyproject.toml`, `docs/conf.py`, FHOPS support alias, release tags. | Sphinx “About FHOPS” page should embed same table (auto-export). | Placeholder committed (`metadata/code_metadata.tex`). |
| Current code version table | Mandatory table with version identifier, permanent link/DOI, dependencies, OS/arch list, CI badge. | `CHANGELOG.md`, GitHub Releases, Zenodo DOI (once minted), CI matrix. | Release notes + Sphinx install guide should pull the same info chunk. | Placeholder committed (`metadata/current_code_version.tex`). |
| Abstract | ≤200 words summarising motivation, software, validation, availability. | Derived after Sections 1–4 are drafted. | High-level abstract reused in docs blog/news. | Planning |
| 1. Motivation and significance | Must state the scientific/operational gap, prior art limits, target users. | `notes/softwarex_manuscript_plan.md` (gaps), `notes/thesis_alignment.md`, Jaffray review, exemplar analysis log. | Feed Sphinx Overview intro + marketing collateral. | Planning |
| 2. Software description | Describe architecture, modules, workflows, dependencies, novel techniques. | `src/` package docs, diagrams from `docs/softwarex/assets/figures`, FHOPS developer docs. | Heavily reused in Sphinx “How FHOPS works” section. Candidate for shared include. | Planning |
| 3. Illustrative example | Provide a reproducible use-case (dataset, solver settings, outputs). | Scripts under `docs/softwarex/manuscript/scripts/`, benchmark telemetry (`assets/data/benchmarks`). | Condensed story becomes quickstart/tutorial chapter. | Planning |
| 4. Impact | Detail adoption, community, extensions, outreach, future potential. | User metrics, citations, workshop notes, roadmap. | Could mirror Sphinx “Impact” page. | Planning |
| 5. Conclusions & future work | Summarise benefits, limitations, roadmap. | FHOPS roadmap, thesis alignment constraints, backlog. | Shared across docs + release blog. | Planning |
| CRediT / Author statement | Required to list contributions per author role. | Author tracker spreadsheet. | Not shared publicly until submission. | Pending |
| Acknowledgements / Funding | Funding sources, compute allocations, partners. | Sponsor list, grant docs. | Some overlap with README acknowledgements. | Planning |
| References | Consolidated BibTeX referencing FHOPS + broader literature. | `manuscript/references.bib`, Jaffray review BibTeX. | Provide subset inside docs referencing style guide. | Seeded |
| Supplementary material | Optional but recommended for extended tables/datasets. | Outputs dumped in `supplementary/` (auto-generated). | Not reused directly, but data may surface in docs. | Scaffolded |

## Cross-linking with Sphinx
- Shared narrative blocks (Overview, architecture descriptions) should live in `sections/includes/` so both the LaTeX manuscript and the Sphinx docs can reuse them.
- Figures/tables: generate sources into `docs/softwarex/assets/figures` and reference them from both outputs to avoid divergence.
- Mapping + include ownership lives in `sections/includes/README.md` (source-of-truth for which snippets sync to which `.rst` files).

## Guide for Authors anchors
- **Highlights:** Max 85 characters per bullet, no citations, must focus on novelty, availability, and validation.
- **Motivation (Section 1):** Explicitly tie to scientific problem + cite the state-of-the-art shortfalls; readers expect measurable gaps.
- **Software description (Section 2):** Include architecture diagrams + usage instructions; document dependencies and performance considerations.
- **Illustrative example (Section 3):** Needs dataset provenance, execution steps, and quantitative/qualitative results demonstrating the software.
- **Impact (Section 4):** Provide adoption indicators (downloads, contributors, partner orgs) and explain who benefits.
- **Conclusions:** Highlight limitations + future development roadmap.
- **Metadata tables:** Required in the main PDF, must match repository/DOI info supplied in the submission portal.

## Next content tasks
1. Assign DRIs for each section (align with FHOPS team workloads and thesis constraints).
2. Stand up `sections/includes/` snippets so Sphinx and the manuscript can share the same paragraphs + tables.
3. Draft Highlights + Abstract once Sections 1–4 reach first-pass completeness.
