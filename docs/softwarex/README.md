# SoftwareX Workspace Structure

Everything related to the FHOPS SoftwareX manuscript lives under this folder. Each subdirectory owns a specific part of the pipeline so we can version templates, source text, and submission artifacts independently.

| Path | Purpose | Current Status |
|------|---------|----------------|
| `reference/` | Locked snapshots of author instructions, official templates, exemplar PDFs, and provenance notes. | ✅ Snapshots captured 2025‑11‑23 (`reference/README.md` lists sources). |
| `manuscript/` | Working tree for the article itself: outline, section drafts, build scripts, and template adaptations. | 🚧 Outline + scaffolding seeded; `latexmk` build + shared include pipeline ready (`manuscript/README.md`). |
| `assets/` | Shared figures/data referenced by the manuscript and Sphinx docs (benchmarks, tuning, playback, costing, scaling). | ✅ `make assets` regenerates everything via scripts under `manuscript/scripts/` (`assets/data/*`, `assets/figures`). |
| `submissions/` | Final submission bundles, cover-letter templates, and portal checklists once we reach Phase 5. | 💤 Not started. |

## Contribution Guidelines

1. **Stay on `feature/softwarex-manuscript`** – all manuscript work happens here until we have a merge-ready drop. Avoid rebasing without coordinating.
2. **Use the automation**:
   - `make assets` (from repo root) runs every script in `manuscript/scripts/` to regenerate datasets, benchmarks, tuners, playback summaries, costing tables, and scaling plots. Regenerated files live under `docs/softwarex/assets/`.
   - `make pdf` (or `make` inside `manuscript/`) builds the LaTeX manuscript via `latexmk`. The PDF lands in `docs/softwarex/manuscript/build/`.
3. **Shared snippets/tables** – edit the Markdown/CSV sources in `manuscript/sections/includes/`. Do **not** hand-edit the generated `.tex`/`.rst` files; `scripts/export_docs_assets.py` recreates them during `make assets`.
4. **Generated telemetry** – JSONL step logs from tuning/playback live in their respective directories. `telemetry/steps/` is ignored; keep only summary CSV/MD/PNG artifacts under version control.
5. **New assets** – add scripts under `manuscript/scripts/` and wire them into `generate_assets.sh`. Document the output path in this README so downstream contributors know what each folder contains.
6. **Submission hygiene** – once we dry-run the Elsevier portal, archive the exported package plus any checklists in `submissions/` with a dated subfolder (`YYYY-MM-DD_dryrun/`).

Questions? Capture assumptions/decisions in `notes/softwarex_manuscript_plan.md` so the plan stays authoritative.
