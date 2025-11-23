# SoftwareX Manuscript Sub-project Change Log

Only changes that affect the SoftwareX planning/manuscript workspace are recorded here. Core FHOPS code/documentation changes still belong in the repository-wide `CHANGE_LOG.md`.

## 2025-11-23 — Workspace scaffolding & exemplar analysis
- Created the `docs/softwarex/` workspace with dedicated `reference/`, `manuscript/`, `assets/`, and `submissions/` folders plus a top-level README describing ownership and next steps.
- Logged provenance for all reference artifacts (Guide for Authors snapshot, elsarticle template bundle, Crossref most-cited dump, nine exemplar PDFs) via `docs/softwarex/reference/README.md`.
- Seeded the manuscript working area: added `manuscript/README.md` outlining the build workflow and `manuscript/outline.md` mirroring the SoftwareX section structure with FHOPS source notes.
- Expanded `notes/softwarex_exemplar_analysis.md` with takeaways + citation-ready cues for all nine exemplar papers to guide drafting and readiness criteria.
- Downloaded the CTAN `elsarticle` template, extracted it into `docs/softwarex/manuscript/elsarticle/`, and updated the manuscript README to record the template snapshot plus next actions.
- Added an initial `fhops-softx.tex` wrapper and a `Makefile` that runs `latexmk -pdf` into `build/`, establishing the traditional TeX Live toolchain for future drafts.
- Added placeholder section includes under `docs/softwarex/manuscript/sections/` (`introduction.tex`, `software_description.tex`, etc.) plus highlights/abstract files, and rewired `fhops-softx.tex` to `\input` them so future drafting is modular.
- Documented the latexmk workflow and TeX Live requirements in `docs/softwarex/manuscript/README.md`.

## 2025-11-24 — Shared content exporter & dataset summaries
- Introduced `scripts/export_docs_assets.py` and wired it into `generate_assets.sh` so all Markdown snippets under `sections/includes/` render automatically into LaTeX + Sphinx-ready `.rst` files during `make assets`.
- Added the first shared narrative (`motivation_story.md`) and included it in both the manuscript and `docs/overview.rst`, ensuring the docs and paper stay synchronized on the FHOPS motivation text.
- Implemented `scripts/run_dataset_inspection.py`, which inspects `examples/minitoy`, `examples/med42`, and a freshly generated `synth --tier small` bundle; outputs JSON summaries + an index under `docs/softwarex/assets/data/datasets/`, and snapshots the synthetic scenario for reproducibility.
- Updated the Phase 1 plan to reflect the completed scenario-ingest automation, keeping the assets checklist aligned with the new scripts.
- Expanded `scripts/generate_assets.sh` so `make assets` now benchmarks `minitoy`, `med42`, and the synthetic tier across SA/ILS/Tabu (with compare presets) and writes per-scenario summaries/telemetry plus an aggregated `benchmarks/index.json`.
- Added a shared heuristic solver matrix/notes pair (`heuristics_matrix.csv`, `heuristics_notes.md`) that the exporter converts into LaTeX/RST so both the manuscript and `docs/howto/heuristic_presets.rst` present identical solver guidance.
- Wired `scripts/run_tuner.py` into the asset pipeline so condensed tuning studies run via `scripts/run_tuning_benchmarks.py` and drop comparison/leaderboard/difficulty tables inside `docs/softwarex/assets/data/tuning/`.
- Added `benchmark_kpis.csv` + `benchmark_kpis_notes.md` and wired them through the exporter so both the manuscript and `docs/howto/benchmarks.rst` can reuse the same SA/ILS/Tabu KPI table.
- Added `scripts/run_playback_analysis.py` plus pipeline hooks that replay the best SA/ILS schedules (deterministic + stochastic) for minitoy, med42, and the synthetic tier, writing shift/day summaries + metrics under `docs/softwarex/assets/data/playback/` for manuscript robustness figures.
