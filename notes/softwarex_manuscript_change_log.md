# SoftwareX Manuscript Change Log (local)

Track local manuscript edits/text debt without polluting the main project CHANGE_LOG. Update this before each writing push.

## 2025-11-24 – Pending text work
- **Section 5 – Conclusions.** Need a proper summary paragraph (recap FHOPS contributions, automation pipeline) plus future work sentence (BC deployments, forwarder/helper backlog). Currently a placeholder.
- **Metadata narrative.** Introduce the metadata tables in Section 1 or 2 (one paragraph explaining release/version, reproducibility log) so reviewers see context before Table refs.
- **Impact metrics references.** Once GitHub/PyPI stats are pulled, add citations/links to show adoption numbers (stars, downloads) rather than qualitative statements.

## 2025-11-27 – Phase 2 asset + reproducibility updates
- Enforced 300 dpi PNG generation inside `scripts/render_prisma_diagram.py` (adds Pillow-backed DPI tagging even when ImageMagick is unavailable) and regenerated `docs/softwarex/assets/figures/prisma_overview.(pdf|png)`; assets now satisfy the SoftwareX resolution requirement.
- Added a “Reproducibility log and environment” subsection to Section~3, tying every benchmark/tuning/playback artefact to its directory, the benchmark log (`docs/softwarex/assets/benchmark_runs.log`), and the recorded hardware/software context (72-core EPYC host, Ubuntu 24.04, Python 3.12.3, Pyomo 6.9.4, HiGHS 1.11.0, FHOPS 1.0.0a2).
- Documented the shared snippet workflow for Sphinx consumers in `docs/includes/softwarex/README.md`, updated the includes README checklist, and re-ran `export_docs_assets.py` so `.tex`/`.rst` outputs stayed in sync.
- Added a reusable CLI pipeline snippet (`sections/includes/cli_pipeline.md` → `.tex/.rst`) that Section~3 now `\input`s, and the same content is included in `docs/howto/benchmarks.rst` to keep manuscript + Sphinx instructions identical.
- Phase 2 close-out checklist added to the planning doc: highlights/abstract/metadata re-proofed, `GH-SWX-Phase2` marked complete, Phase 3 validation/submission bundle/metadata tasks staged with concrete commands and directory requirements.
- Section~\ref{sec:software-description} now includes the exact FHOPS MIP formulation (objective, decision variables, constraints, set/parameter definitions), satisfying the request to document the mathematical model reviewers will evaluate.

## 2025-11-24 – Section polish
- Added CLI/asset-path references in Section 1 and Section 3 so every table/figure cites its source directory (e.g., `docs/softwarex/assets/data/benchmarks/<slug>/summary.csv`, `docs/softwarex/assets/data/tuning`).
- Expanded Section 2 automation notes with concrete command examples and asset destinations.
- Rewrote Section 4 to highlight how FHOPS addresses Jaffray et al. gaps, emphasising BC focus today with extensibility for other regions/currencies later.
- Section 5 now references the backlog in `notes/softwarex_manuscript_change_log.md` so future work is tied to an actionable list.
- Added explicit CLI/source references after Tables~\ref{tab:benchmarks}--\ref{tab:tuning} and in the playback/costing paragraph so readers know which directories (\texttt{docs/softwarex/assets/...}) contain each artefact; noted CAD currency assumption and path to alternative machine-rate files.

---

## Imported entries from legacy manuscript CHANGELOG

### 2025-11-26 — PRISMA automation + shared figure embed
- Rebuilt `prisma_overview.tex` using plain TikZ (no external packages) and added a standalone driver so the figure can compile independently of the manuscript.
- Added `scripts/render_prisma_diagram.py` and wired it into `scripts/generate_assets.sh`; running `make assets` now regenerates `docs/softwarex/assets/figures/prisma_overview.(pdf|png)` automatically (SVG generated opportunistically when `pdf2svg` is installed).
- Updated `docs/overview.rst` to embed the PNG alongside the narrative include, ensuring the user guide displays the exact same visual as the manuscript.
- Documented the automated workflow in `docs/softwarex/manuscript/README.md` and `sections/includes/README.md`, and marked the Phase 1 PRISMA task complete inside `notes/softwarex_manuscript_plan.md` / `notes/submission_readiness_dashboard.md`.
- Introduced `FHOPS_ASSETS_FAST` handling inside `scripts/generate_assets.sh` (cuts benchmark/tuning budgets for quick iterations) and captured the manual verification checklist + env-var guidance in `docs/softwarex/manuscript/README.md`. The submission readiness dashboard now references the canonical figure assets.
- Added `scripts/run_manuscript_benchmarks.sh` plus new Makefile targets (`make manuscript-benchmarks`, `make manuscript-benchmarks-fast`) so we can rerun the entire asset pipeline on demand, log runtimes + asset hashes to `docs/softwarex/assets/benchmark_runs.log`, and satisfy the reproducibility checklist captured in `notes/submission_readiness_dashboard.md`.

### 2025-11-25 — PRISMA workflow figure wiring
- Inserted the PRISMA-style workflow include (`\input{sections/includes/prisma_overview}`) into `sections/software_description.tex`, anchoring the architecture narrative around the same figure used in the WS3 EI manuscript pattern.
- Created `docs/includes/softwarex/prisma_overview.rst`, an interim narrative-only include so the Sphinx Overview can cite the same pipeline until we export a PNG version of the diagram.
- Updated `docs/overview.rst` to include the new snippet under an “Automation pipeline” section, keeping the user guide aligned with the manuscript narrative ahead of the future PNG/SVG export workflow.
- Updated `docs/softwarex/manuscript/sections/includes/README.md` with maintenance notes for the PRISMA figure (package requirements, manual regeneration steps, future PNG workflow) and tracked the work inside `notes/softwarex_manuscript_plan.md`.
- Expanded `notes/thesis_alignment.md` with explicit Chapter 2 case-study definitions (coastal skyline/tethered, interior community forest, salvage/MPB) plus checkpoint dates (dataset freeze, scenario cartridge export, solver alignment, KPI drafting, thesis submission) so we can reference a single source when validating SoftwareX scope boundaries.

### 2025-11-24 — Shared content exporter & dataset summaries
- Introduced `scripts/export_docs_assets.py` and wired it into `generate_assets.sh` so all Markdown snippets under `sections/includes/` render automatically into LaTeX + Sphinx-ready `.rst` files during `make assets`.
- Added the first shared narrative (`motivation_story.md`) and included it in both the manuscript and `docs/overview.rst`, ensuring the docs and paper stay synchronized on the FHOPS motivation text.
- Implemented `scripts/run_dataset_inspection.py`, which inspects `examples/tiny7`, `examples/med42`, and a freshly generated `synth --tier small` bundle; outputs JSON summaries + an index under `docs/softwarex/assets/data/datasets/`, and snapshots the synthetic scenario for reproducibility.
- Updated the Phase 1 plan to reflect the completed scenario-ingest automation, keeping the assets checklist aligned with the new scripts.
- Expanded `scripts/generate_assets.sh` so `make assets` now benchmarks `tiny7`, `med42`, and the synthetic tier across SA/ILS/Tabu (with compare presets) and writes per-scenario summaries/telemetry plus an aggregated `benchmarks/index.json`.
- Added a shared heuristic solver matrix/notes pair (`heuristics_matrix.csv`, `heuristics_notes.md`) that the exporter converts into LaTeX/RST so both the manuscript and `docs/howto/heuristic_presets.rst` present identical solver guidance.
- Wired `scripts/run_tuner.py` into the asset pipeline so condensed tuning studies run via `scripts/run_tuning_benchmarks.py` and drop comparison/leaderboard/difficulty tables inside `docs/softwarex/assets/data/tuning/`.
- Added `benchmark_kpis.csv` + `benchmark_kpis_notes.md` and wired them through the exporter so both the manuscript and `docs/howto/benchmarks.rst` can reuse the same SA/ILS/Tabu KPI table.
- Added `scripts/run_playback_analysis.py` plus pipeline hooks that replay the best SA/ILS schedules (deterministic + stochastic) for tiny7, med42, and the synthetic tier, writing shift/day summaries + metrics under `docs/softwarex/assets/data/playback/` for manuscript robustness figures.
- Added `scripts/run_costing_demo.py`, which exercises `fhops dataset estimate-cost` for representative med42 machines, logs telemetry JSONL, and emits `cost_summary.csv/json` under `docs/softwarex/assets/data/costing/` for the machine-rate discussion.
- Added `scripts/run_synthetic_sweep.py` so we can regenerate synthetic small/medium/large tiers, benchmark SA runtimes, and capture `scaling_summary.csv/json` plus `runtime_vs_blocks.png` under `docs/softwarex/assets/data/scaling/`.

### 2025-11-23 — Workspace scaffolding & exemplar analysis
- Created the `docs/softwarex/` workspace with dedicated `reference/`, `manuscript/`, `assets/`, and `submissions/` folders plus a top-level README describing ownership and next steps.
- Logged provenance for all reference artifacts (Guide for Authors snapshot, elsarticle template bundle, Crossref most-cited dump, nine exemplar PDFs) via `docs/softwarex/reference/README.md`.
- Seeded the manuscript working area: added `manuscript/README.md` outlining the build workflow and `manuscript/outline.md` mirroring the SoftwareX section structure with FHOPS source notes.
- Expanded `notes/softwarex_exemplar_analysis.md` with takeaways + citation-ready cues for all nine exemplar papers to guide drafting and readiness criteria.
- Downloaded the CTAN `elsarticle` template, extracted it into `docs/softwarex/manuscript/elsarticle/`, and updated the manuscript README to record the template snapshot plus next actions.
- Added an initial `fhops-softx.tex` wrapper and a `Makefile` that runs `latexmk -pdf` into `build/`, establishing the traditional TeX Live toolchain for future drafts.
- Added placeholder section includes under `docs/softwarex/manuscript/sections/` (`introduction.tex`, `software_description.tex`, etc.) plus highlights/abstract files, and rewired `fhops-softx.tex` to `\input` them so future drafting is modular.
- Documented the latexmk workflow and TeX Live requirements in `docs/softwarex/manuscript/README.md`.
