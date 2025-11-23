# SoftwareX Workspace Structure

Everything related to the FHOPS SoftwareX manuscript lives under this folder. Each subdirectory owns a specific part of the pipeline so we can version templates, source text, and submission artifacts independently.

| Path | Purpose | Current Status |
|------|---------|----------------|
| `reference/` | Locked snapshots of author instructions, official templates, exemplar PDFs, and provenance notes. | ✅ Snapshots captured 2025‑11‑23 (`reference/README.md` lists sources). |
| `manuscript/` | Working tree for the article itself: outline, section drafts, build scripts, and template adaptations. | 🚧 Outline + scaffolding seeded (see `manuscript/README.md`). |
| `assets/` | Shared figures/data referenced by the manuscript and, eventually, Sphinx docs. | 🚧 Empty placeholders for now (`assets/figures`, `assets/data`). |
| `submissions/` | Final submission bundles, cover-letter templates, and portal checklists once we reach Phase 5. | 💤 Not started. |

**Next additions**
1. Wire `manuscript/` to the Elsevier `elsarticle` template and add a reproducible build command (likely via `latexmk` or `tectonic`).
2. Drop reusable diagrams/tables into `assets/` so both the manuscript and the Sphinx docs can share source files.
3. When we dry-run the submission portal, capture the checklist + exported package under `submissions/`.
