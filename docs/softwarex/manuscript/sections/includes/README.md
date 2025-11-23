# Shared Include Plan (Sphinx ↔ SoftwareX Manuscript)

The `sections/includes/` directory hosts text blocks and table fragments that must stay identical between the SoftwareX LaTeX manuscript and the FHOPS Sphinx documentation. Source-of-truth will live here as Markdown/CSV, then export scripts will render:

1. `*.tex` – pulled into `fhops-softx.tex` via `\input{sections/includes/...}`
2. `*.rst` – included from the Sphinx tree via ``.. include::`` directives (or Copied into appropriate RST files during doc builds)

Automation hook (Phase 1 deliverable): extend `docs/softwarex/manuscript/scripts/export_docs_assets.py` so `make assets` produces both output formats from the Markdown/CSV primaries.

## Mapping table

| Manuscript Section | Primary Sphinx Source(s) | Planned include(s) | Notes / Tasks |
|--------------------|--------------------------|--------------------|---------------|
| 1. Motivation & significance | `docs/overview.rst`, `docs/roadmap.rst`, `notes/thesis_alignment.md` | `motivation_story.md` → `motivation_story.tex/.rst` | Explain real modelling gaps (open tooling, integrated workflows) and cite Jaffray review. Keep BC case-study carve-out for Rosalia. |
| 2. Software description – Architecture | `docs/reference/architecture.rst`, `docs/howto/system_sequencing.rst`, `docs/api/*` | `architecture_summary.md`, `pipeline_diagram.*` | Text + figure describing scenario→solver→playback pipeline. Manuscript figure reused in docs `overview`. |
| 2. Software description – Heuristics/tuners | `docs/howto/heuristic_presets.rst`, `docs/howto/parallel_heuristics.rst`, `docs/howto/tabu.rst`, `docs/howto/ils.rst`, `docs/howto/telemetry_tuning.rst` | `heuristic_matrix.csv` + `heuristic_text.md` | CSV drives both manuscript table and Sphinx reference page; describe SA/ILS/Tabu + tuner automation. |
| 3. Illustrative example | `docs/howto/quickstart.rst`, `docs/howto/benchmarks.rst`, `docs/howto/synthetic_datasets.rst` | `illustrative_walkthrough.md`, `benchmark_table.csv` | Align CLI steps + dataset notes; reuse same telemetry screenshots. |
| 4. Impact | `docs/roadmap.rst`, `docs/references/adoption.rst`, release notes | `impact_story.md` | Summarize adoption + roadmap commitments once metrics ready. |
| Metadata tables | `docs/softwarex/reference/README.md`, `README.md`, `pyproject.toml` | `metadata_basics.yaml` | Single YAML feeds both LaTeX metadata tables and Sphinx “About FHOPS” page. |

## Action items

- [x] Draft `motivation_story.md` (source-of-truth) keyed to Guide-for-Authors requirements; wire exporter to emit `.tex` + `.rst`.
- [ ] Define template + script for table exports (heuristics, benchmark KPIs) so Sphinx and LaTeX stay in sync.
  - [x] Heuristics solver matrix now lives in `heuristics_matrix.csv` + `heuristics_notes.md` and renders into TeX/RST.
  - [x] Benchmark KPI table + notes now live in `benchmark_kpis.csv` + `benchmark_kpis_notes.md`.
- [x] Update Sphinx `overview.rst` and `docs/templates/includes/` to ``.. include::`` the generated `.rst` snippets once available (see `docs/overview.rst` motivation section).
- [ ] Add CI check (Phase 3) to confirm no drift between `.md` primaries and rendered assets.
- [ ] PRISMA figure maintenance
  - [x] Store the LaTeX source in `prisma_overview.tex` (requires the `prisma-flow-diagram` package, already added to `fhops-softx.tex` preamble).
  - [x] Provide a docs include (`docs/includes/softwarex/prisma_overview.rst`) describing the same flow until we land an automated PNG export.
  - [ ] Extend `export_docs_assets.py` (or a companion script) to emit a vector/PNG asset so Sphinx can embed the exact diagram.
  - [ ] Update `docs/overview.rst` to include the exported figure once the PNG workflow exists.

### PRISMA figure workflow (manual process for now)

1. Source file: `prisma_overview.tex` (lives beside the other includes). It uses
   `prisma-flow-diagram`, so the manuscript preamble (`fhops-softx.tex`) already loads that
   package.
2. To regenerate the PDF locally, run:

   ```bash
   cd docs/softwarex/manuscript
   latexmk -lualatex -halt-on-error -interaction=nonstopmode \
       -jobname=prisma_overview sections/includes/prisma_overview.tex
   ```

   This writes `sections/includes/prisma_overview.pdf` which we can commit or use as the
   source for PNG/SVG exports.
3. Until we automate PNG/SVG creation, note the manual conversion step (requires ImageMagick
   or Ghostscript):

   ```bash
   magick -density 300 sections/includes/prisma_overview.pdf \
       docs/softwarex/assets/figures/prisma_overview.png
   ```

   (Any subsequent automation should follow this naming/location convention so the docs can
   include the raster asset.)
4. After regenerating the diagram, run `make assets` to refresh any dependent snippets and
   confirm the Sphinx include (`docs/includes/softwarex/prisma_overview.rst`) still reflects
   the latest narrative/links.

These steps should be replaced by a scripted workflow (Phase 1 remaining task), but having
explicit manual instructions here prevents drift in the meantime.

> Ownership: Lead author (Gregory Paradis). Automation support: Codex tasks under Phase 1 asset/export work.
