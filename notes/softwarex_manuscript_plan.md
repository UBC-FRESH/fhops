# SoftwareX Manuscript Rollout Plan

> **Planning Note:** Every task must use checkboxes and include subtasks/sub-subtasks as needed. Keep expanding items in-place as execution details emerge so we stay consistent with this structure.
>
> **Citation Guardrail:** Until Rosalia Jaffray’s thesis chapters are defended/public, only cite the submitted systematic review (“Jaffray, Coupland, Paradis, *Forest harvesting operational planning tools…*, submitted to IJFE 2025/10”) and the published papers it covers. Do **not** cite unreleased thesis chapters or drafts in the SoftwareX manuscript.

## Goals
- [ ] Author a SoftwareX manuscript that showcases FHOPS and complements the existing Sphinx user guide (especially the Overview section).
  - [ ] Distill the narrative arc (problem, contribution, impact) tailored for SoftwareX readership.
  - [ ] Identify sections that can be shared with or reused inside the Sphinx Overview for consistency.
  - [ ] Capture reviewer-ready figures/tables list aligned with FHOPS differentiators.
- [ ] Create a reusable `docs/softwarex/` subfolder that can eventually surface key manuscript content in the broader documentation set.
  - [x] Define the subfolder layout (manuscript, reference, assets, submissions, automation).
  - [x] Wire up scripts or Make targets for building/checking manuscript assets.
  - [ ] Document contribution guidelines for manuscript files inside README.
- [ ] Follow SoftwareX author instructions precisely, benchmark readiness using exemplar publications, and integrate the Jaffray MASc literature review so citations lean on the broader forestry/OR canon.
  - [ ] Track the authoritative author guidelines version/date in repository metadata.
  - [ ] Maintain a checklist derived from instructions for ongoing compliance.
  - [x] Log insights/benchmarks from exemplar papers to inform quality gates.
  - [ ] Mirror the Jaffray MASc literature review (see `tmp/jaffray-rosalia-masc-proposal/`) into our BibTeX + outline so real forestry/OR papers anchor each section.
  - [ ] Coordinate with Rosalia Jaffray’s thesis deliverables so Chapter 2 (multi-case FHOPS deployment) remains novel; FHOPS SoftwareX paper should highlight the tooling while deferring detailed BC case-study analysis to her thesis timeline.
- [x] Lock single-author ownership and correspondence details for submission materials.
  - [x] Gregory Paradis is sole author and corresponding contact for FHOPS SoftwareX manuscript.
  - [x] Use Faculty of Forestry, University of British Columbia affiliation and `gregory.paradis@ubc.ca` for all metadata (mirrors WS3 EI submission).

## Phase 0 – Planning (Now)
- [x] Capture requirements: Download the latest SoftwareX author instructions (PDF + any LaTeX/Word templates) into `docs/softwarex/reference/` and version them.
  - [x] Confirm the most recent instruction set from Elsevier/SoftwareX site.
  - [x] Download PDF instructions plus LaTeX/Word templates.
  - [x] Store raw artifacts under `docs/softwarex/reference/` with README describing provenance.
  - [x] Add version/date annotations to help track updates over time.
- [x] Build reference library: Collect 3–5 high-quality SoftwareX FH/optimization papers (PDF + citation metadata) inside `docs/softwarex/reference/examples/` with comparison notes.
  - [x] Curate candidate exemplar papers relevant to optimization frameworks.
  - [x] Download PDFs and save citation metadata (BibTeX/DOI) alongside each example.
  - [x] Write short benchmarking notes (strengths, structure cues, submission requirements) per exemplar.
- [x] Align scope: Define manuscript success criteria, key story beats, figures/tables to reuse from docs, and how content will feed into Sphinx Overview.
  - [x] Draft success criteria (acceptance goals, technical coverage, evaluation depth).
  - [x] List candidate figures/tables pulled from existing docs or experiments.
  - [x] Map each manuscript section to overlapping Sphinx content to avoid duplication.
- [x] Decide workflow tooling: Choose manuscript format (LaTeX vs. Markdown-to-PDF pipeline), bibliography management, and automation hooks (e.g., `make manuscript`).
  - [x] Evaluate tooling options (LaTeX template vs. MyST/pandoc flow) against SoftwareX requirements (chose LaTeX/latexmk).
  - [x] Select bibliography tooling (BibTeX `references.bib`, seeded with exemplar + Jaffray references).
  - [x] Define automation commands/scripts for building manuscript artifacts (`Makefile` + `latexmk`).
- [x] Establish timeline & ownership: Turn phases into GitHub issues/milestones, map DRI(s), and set review checkpoints that align with FHOPS releases.
  - [x] Convert each phase into one or more GitHub issues with owners/due dates.
    - [x] `GH-SWX-Phase0` – Planning wrap-up (DRI: Lead author, due 2025-11-23, status: complete in this commit).
    - [x] `GH-SWX-Phase1` – Manuscript architecture & repo scaffolding (DRI: Lead author, support: Codex automation, due 2025-12-07, tied to FHOPS `v1.0.0-beta` prep).
    - [x] `GH-SWX-Phase2` – Content drafting sprint covering Sections 1–3 (DRI: Lead author, support: Rosalia for literature cross-checks, due 2025-12-21).
    - [x] `GH-SWX-Phase3` – Validation + artifact packaging (DRI: Lead author with Codex automation assist, reviewer: Lead author, due 2026-01-04, just ahead of FHOPS `v1.0.0-rc1`).
    - [x] `GH-SWX-Phase4` – Internal review & iteration (DRI: Lead author, reviewers: Rosalia + FHOPS core, due 2026-01-18).
    - [x] `GH-SWX-Phase5` – Submission prep & portal rehearsal (DRI: Lead author, due 2026-02-01, aligns with `v1.0.0` GA).
    - [x] `GH-SWX-Phase6` – Post-submission tracking (DRI: Lead author until decision, then shared).
  - [x] Align manuscript milestones with FHOPS release cadence.
    - [x] Scaffolding (Phase1) completes before `v1.0.0-beta` branch cut so docs + manuscript share assets.
    - [x] Drafting (Phase2) and validation (Phase3) line up with `v1.0.0-rc1`, ensuring benchmark scripts match release-candidate code.
    - [x] Submission readiness (Phase4–5) lands just after `v1.0.0` GA so we can cite a stable tag in the manuscript/Zenodo deposit.
  - [x] Schedule recurring review checkpoints (internal review, doc sync, artifact verification).
    - [x] Weekly Monday FHOPS manuscript sync (30 min) for status + blockers through Phase5.
    - [x] Bi-weekly Thursday artifact review (automation + benchmark verification) during Phases2–3.
    - [x] Pre-submission editorial review 3 days before portal upload (Phase5) with Rosalia + FHOPS docs lead.

> Phase 0 exit status (2025-11-23): Requirements captured, exemplar set curated, tooling decisions locked, and the timeline/ownership grid is now committed—ready to advance to Phase 1 tasks.

## Phase 1 – Manuscript Architecture & Repo Scaffolding
- [ ] Stand up `docs/softwarex/manuscript/` with template files (main manuscript, supplementary material, metadata).
  - [x] Copy the selected SoftwareX template into the repo structure.
  - [x] Prepare placeholders for supplementary files and metadata tables.
  - [x] Add README describing how to compile and where outputs land.
- [ ] Create a section-by-section outline that mirrors SoftwareX structure (Abstract, Software Metadata, etc.) and cross-reference planned FHOPS documentation tie-ins.
  - [x] List required sections per SoftwareX guidelines.
  - [x] For each section, note primary FHOPS content sources (code, docs, experiments).
  - [x] Highlight sections that need coordination with Sphinx to reuse text.
- [ ] Draft a mapping document showing what portions can be shared with Sphinx (e.g., Overview narrative, feature tables).
  - [x] Identify overlapping narrative components.
  - [x] Decide on shared include files or content fragments.
  - [x] Document synchronization process between manuscript and Sphinx (see `docs/softwarex/manuscript/sections/includes/README.md`).
- [ ] Establish build scripts/notebooks for regenerating figures, tables, and performance benchmarks referenced in the paper.
  - [x] Inventory required figures/tables and their data sources.
    - `benchmark_kpis.csv` / `benchmark_kpis_notes.md` → shared solver comparison table (source: `generate_assets.sh` → `fhops bench suite` runs under `docs/softwarex/assets/data/benchmarks/`).
    - Tuning leaderboard/comparison (`docs/softwarex/assets/data/tuning/tuner_*.(csv|md)`) → `run_tuner.py` + `scripts/run_tuning_benchmarks.py`.
    - Playback summaries (`docs/softwarex/assets/data/playback/**/shift.csv`, `day.csv`, `metrics.json`, `summary.md`) → `run_playback_analysis.py`.
    - Cost summary (`docs/softwarex/assets/data/costing/cost_summary.{csv,json}`) → `run_costing_demo.py`.
    - Scaling plot/table (`docs/softwarex/assets/data/scaling/runtime_vs_blocks.png`, `scaling_summary.{csv,json}`) → `run_synthetic_sweep.py`.
    - Dataset index + summaries (`docs/softwarex/assets/data/datasets/index.json`, `*_summary.json`) → `run_dataset_inspection.py`.
    - PRISMA-style FHOPS workflow diagrams (architecture + evaluation flow) → `manuscript/sections/includes/prisma_overview.tex` rendered via `scripts/render_prisma_diagram.py` (drives PDF/PNG assets for both manuscript + docs). Consider hierarchical variants (full FHOPS stack + zoomed-in evaluation loop).
  - [x] Create reproducible scripts/notebooks to regenerate each artifact.
  - [x] Integrate artifact generation into CI or a manual checklist (`make manuscript-benchmarks` logs runs + hashes to `docs/softwarex/assets/benchmark_runs.log`; `manuscript-benchmarks-fast` mirrors the quick sanity check).
- [x] PRISMA-style diagram workflow (WS3 EI-inspired).
  - [x] Draft `sections/includes/prisma_overview.tex` capturing scenario ingest → solver core → telemetry/export path with the `prisma-flow-diagram` package.
    - [x] Reference the include inside `sections/software_description.tex` so the manuscript narrative now calls out Figure~\ref{fig:fhops-prisma-overview}.
  - [x] Mirror the figure in Sphinx via `docs/includes/softwarex/prisma_overview.rst` (and eventually an exported PNG) so both outputs stay aligned.
    - [x] Add an interim narrative-only include (`docs/includes/softwarex/prisma_overview.rst`) so the docs reference the same pipeline until we export a PNG.
    - [x] Hook the include into the Sphinx Overview page so the docs surface the same workflow description.
    - [x] Add a PNG export workflow so the visual matches the manuscript and can be embedded directly in Sphinx (SVG optional when `pdf2svg` is installed).
  - [x] Document update instructions (package requirements, automation hooks) in `docs/softwarex/manuscript/sections/includes/README.md` and tag figure assets inside `notes/submission_readiness_dashboard.md`.
- [ ] Asset-generation plan:
  - [x] **Scenario ingest demo:** Script (`scripts/run_dataset_inspection.py`) that inspects `examples/minitoy` + `examples/med42`, generates a fresh `synth generate --tier small` bundle, and emits schema summaries in `docs/softwarex/assets/data/datasets/`.
  - [x] **Benchmark sweep (SA baseline):** Extend `scripts/generate_assets.sh` (already running SA on `minitoy`) to include `med42` + `synthetic-small`. Use `fhops bench suite --telemetry-log --compare-preset ...` so we capture CSV/JSON telemetry for each scenario. Goal: PyDDRBG-style benchmark manifest.
  - [x] **Solver comparison (SA vs. ILS vs. Tabu):** Add a script (or extend the benchmark script) that runs `fhops bench suite --include-ils --include-tabu` on `minitoy` + `med42`, producing tables comparing objective/runtime/KPIs per solver. Provide LaTeX table for manuscript.
  - [x] **Hyperparameter tuning harness:** Script (`scripts/run_tuner.py`) that launches short Optuna-style studies (via `scripts/run_tuning_benchmarks.py`) for minitoy, med42, and the synthetic tier. Results live under `docs/softwarex/assets/data/tuning/` (telemetry + comparison/leaderboard CSV/MD).
  - [x] **Playback + KPI reporting:** Script (`scripts/run_playback_analysis.py`) that takes the best SA/ILS assignments, runs deterministic + stochastic playback, computes day/shift KPIs, and exports CSV/Markdown summaries under `docs/softwarex/assets/data/playback/`.
  - [x] **Stochastic robustness tests:** As part of the playback script, run multi-sample playback (50 samples with downtime/weather/landing shocks) and capture metrics JSON + summaries per scenario/solver for manuscript figure/table hooks.
  - [x] **Costing demo:** Script (`scripts/run_costing_demo.py`) that runs `fhops dataset estimate-cost` on med42 machines, captures telemetry JSONL, and exports `cost_summary.csv/json` under `docs/softwarex/assets/data/costing/`.
  - [x] **Synthetic scaling sweep:** Script (`scripts/run_synthetic_sweep.py`) that generates synthetic small/medium/large tiers (fixed RNG seeds), runs a single SA pass per tier, and plots runtime vs. scenario size (`scaling_summary.csv/json` + `runtime_vs_blocks.png`).
  - [ ] **Documentation/export assets:** Script (`scripts/export_docs_assets.py`) that outputs tables used in the manuscript (harvest system registry excerpt, operator preset table) in CSV + LaTeX format for direct inclusion.
    - [x] Share heuristic solver matrix + notes (`heuristics_matrix.csv` + `.md`) across manuscript + Sphinx via the exporter.
    - [x] Render shared narrative snippets from Markdown → LaTeX/RST (integrated into `generate_assets.sh`).
- [ ] Capture thesis alignment: Document touchpoints with `tmp/jaffray-rosalia-masc-proposal` / `tmp/jaffray-rosalia-masc-thesis` in `notes/thesis_alignment.md` and weave key citations into each section outline.
  - [x] Explicitly list which FHOPS analytical content will be reserved for Jaffray Chapter 2 (two-to-three BC case studies answering the open questions from her intro/lit review).
  - [ ] Ensure the SoftwareX single-author paper focuses on platform architecture, reproducibility, and tooling; detailed BC case-study insights remain embargoed until Rosalia submits/publishes her thesis work.

## Phase 2 – Content Drafting
- [ ] Produce first-pass text for each major section, incorporating FHOPS capabilities, unique contributions, and methodology.
  - [ ] Draft Abstract, Intro, and Software Metadata sections.
    - [x] Section~1 (Motivation \& significance) updated with Jaffray review context + contribution framing.
    - [x] Highlights + abstract drafted to emphasise the reproducible workflow and thesis alignment.
    - [x] Abstract outline aligned with exemplar structure (PyLESA/cashocs style).
    - [x] Software Metadata tables (code metadata + current code version) populated with release/licensing/reproducibility details.
  - [ ] Document Implementation/Architecture details referencing FHOPS internals.
  - [ ] Summarize Impact and Future Work narratives.
- [ ] Generate required assets: architecture diagrams, workflow figures, tables summarizing problem classes, benchmark results.
  - [ ] Update or design new diagrams highlighting FHOPS pipeline.
  - [ ] Prepare performance/benchmark tables with accompanying captions.
  - [ ] Validate figure resolution/format meets SoftwareX standards.
- [ ] Capture reproducibility details (dataset descriptions, parameter choices, environment info) alongside manuscript text for later validation.
  - [ ] Log datasets, solver settings, and hardware/software environments.
  - [ ] Store experiment configuration files or references in repo.
  - [ ] Tie each reproducibility note to a manuscript section for traceability.
- [ ] Keep snippets modular so they can be embedded into Sphinx using includes or shared source files.
  - [ ] Factor reusable text blocks into shared include files.
  - [ ] Add guidance in Sphinx docs for pulling in manuscript excerpts.
  - [ ] Test include flow to ensure formatting parity between outputs.

## Phase 3 – Technical Validation & Artifact Packaging
- [ ] Verify all experiments/benchmarks are scripted and reproducible (CI or documented commands).
  - [ ] Audit experiment scripts for completeness and determinism.
  - [ ] Ensure datasets and environment specs are accessible or documented.
  - [ ] Execute dry-run reproductions and capture logs/results.
- [ ] Assemble the companion artifact package (code pointers, sample data, notebooks) expected by SoftwareX.
  - [ ] Define the package structure and README per SoftwareX artifact policy.
  - [ ] Bundle minimal datasets or links required to run FHOPS demos.
  - [ ] Capture checksums and storage locations for future reference.
- [ ] Sync documentation assets: confirm figures/tables render correctly both in manuscript and Sphinx.
  - [ ] Test rendering pipeline for manuscript (PDF) and Sphinx (HTML/PDF).
  - [ ] Fix styling/resolution issues detected in either output.
  - [ ] Document any format-specific modifications needed.
- [ ] Run linting/formatting on manuscript sources (e.g., `latexmk`, `pandoc`, or Vale) and set up automated checks if possible.
  - [ ] Choose linting/QA tools applicable to chosen manuscript stack.
  - [ ] Integrate linting commands into CI or pre-commit hooks.
  - [ ] Track lint results and resolve outstanding warnings/errors.

## Phase 4 – Internal Review & Iteration
- [ ] Conduct structured reviews (technical accuracy, narrative clarity, editorial polish) with the FHOPS team.
  - [ ] Schedule review sessions per discipline (technical, editorial, UX).
  - [ ] Capture feedback in a centralized tracker with owners/due dates.
  - [ ] Verify each comment is resolved or explicitly deferred.
- [ ] Perform cross-checks with docs team to avoid conflicting messaging and to harvest reusable copy for the user guide.
  - [ ] Share manuscript excerpts earmarked for Sphinx integration.
  - [ ] Confirm terminology and feature descriptions match documentation updates.
  - [ ] Synchronize release timing between manuscript and docs refresh.
- [ ] Address reviewer comments, track decisions, and update the reference library benchmarks if new exemplars emerge.
  - [ ] Log all comment dispositions (accepted, rejected with rationale, needs follow-up).
  - [ ] Update exemplar benchmarking notes if new insights surface.
  - [ ] Record lessons learned for future submissions.
- [ ] Freeze near-final draft and tag associated FHOPS release/artifacts for traceability.
  - [ ] Tag git commits/releases that correspond to the submission snapshot.
  - [ ] Archive artifact bundles with hashes.
  - [ ] Communicate freeze status to contributors and lock files if necessary.

## Phase 5 – Submission Preparation
- [ ] Complete SoftwareX submission requirements: cover letter, metadata forms, graphical abstract (if required), highlights.
  - [ ] Draft and review the cover letter tailored to SoftwareX scope.
  - [ ] Fill out metadata forms and cross-verify author details.
  - [ ] Produce graphical abstract/highlights complying with specs.
- [ ] Validate formatting against SoftwareX checklist (word count, references, figure resolution, file formats).
  - [ ] Run final word/character counts and compare to limits.
  - [ ] Check references for completeness and formatting accuracy.
  - [ ] Confirm figure/table resolutions and file types meet portal rules.
- [ ] Finalize licensing statements, acknowledgments, funding info, and ORCID data.
  - [ ] Gather required acknowledgments/funding statements from team.
  - [ ] Ensure each author’s ORCID and affiliation is up to date.
  - [ ] Validate licensing terms against FHOPS project constraints.
- [ ] Dry-run the submission portal workflow, then submit and archive the submitted package (plus hashes) in `docs/softwarex/submissions/`.
  - [ ] Perform portal rehearsal to confirm required uploads and fields.
  - [ ] Submit final package and capture confirmation receipts.
  - [ ] Archive submitted materials plus checksums in `docs/softwarex/submissions/`.

## Phase 6 – Post-Submission & Publication Integration
- [ ] Track editor/reviewer correspondence, store decision letters/responses, and update plan with action items.
  - [ ] Centralize communications in repo (redacted if needed) or shared tracker.
  - [ ] Extract tasks from decision letters and slot them into appropriate phases.
  - [ ] Update checklist status after each correspondence round.
- [ ] Implement requested revisions, keeping docs/softwarex and Sphinx content in sync.
  - [ ] Apply manuscript edits per reviewer feedback with change tracking.
  - [ ] Reflect accepted changes in Sphinx or other docs where relevant.
  - [ ] Re-run validation steps for any updated experiments/assets.
- [ ] Upon acceptance, prepare camera-ready files, Zenodo/DOI deposits, and cross-link from FHOPS docs, README, and release notes.
  - [ ] Incorporate copyeditor changes and final templates.
  - [ ] Deposit artifacts/data with DOI services (e.g., Zenodo) and record links.
  - [ ] Update README, website, and release notes with publication details.
- [ ] Celebrate release, publish announcements, and schedule periodic refreshes of manuscript-aligned documentation.
  - [ ] Draft blog posts/social announcements summarizing acceptance.
  - [ ] Share internal recap/retrospective for lessons learned.
  - [ ] Set reminders for periodic manuscript/doc alignment reviews.

## Immediate Next Actions
- [x] Wire the PRISMA overview figure into both outputs.
  - [x] `\input{sections/includes/prisma_overview}` inside the Software Description narrative to visually anchor the workflow story.
  - [x] Confirm the matching `docs/includes/softwarex/prisma_overview.rst` renders in Sphinx (Overview page) and add instructions for refreshing it when the TikZ source changes.
    - [x] Land the interim narrative-only include so Sphinx can reference the same flow even before we have PNG exports.
    - [x] Update the Sphinx overview to ``.. include::`` the snippet so readers see the workflow summary, plus embed the auto-generated PNG.
    - [x] Document the PNG export workflow (via `render_prisma_diagram.py` + `generate_assets.sh`) so refresh instructions live alongside the include metadata.
  - [x] Record figure provenance inside `docs/softwarex/manuscript/sections/includes/README.md` so future changes stay deterministic.
- [x] Kick off Phase 2 drafting for Sections 1–3 while the automation context is fresh.
  - [x] Use `notes/softwarex_exemplar_analysis.md` takeaways and the Jaffray systematic review references to outline the Intro and Software Metadata paragraphs.
  - [x] Draft the first pass of the Motivation/Contribution narrative (Section 1) using the shared snippets in `sections/includes/motivation_story.md`.
  - [x] Capture open questions / text debt in the local manuscript change log before each writing push so we can trace edits without touching the main FHOPS changelog. (See `notes/softwarex_manuscript_change_log.md`.)
  - [x] Add metadata-context paragraph in the introduction referencing Tables~\ref{tab:code-metadata} and \ref{tab:current-code-version}.
  - [x] Draft Section~5 (Conclusions) summarising FHOPS contributions and future work.
- [x] Re-run heuristic benchmarks with realistic runtimes/iteration counts (see `notes/coding-agent-conversation-log.txt` discussion on MIP vs. heuristic time scale).
  - [x] Derive a target runtime per scenario by solving the MIP baseline (HiGHS) or reusing prior solver logs; heuristics must run within 0.1–10× of that wall clock.
  - [x] Update `scripts/generate_assets.sh` (or override via env vars) so SA ≥ 6 000 iterations, ILS ≥ 1 000 perturb/local-search cycles, Tabu stall/iteration budgets ≥ 10 000 and time limit ≥ 600 s for med42; keep fast-mode overrides documented.
  - [x] Execute `FHOPS_ASSETS_FAST=0 docs/softwarex/manuscript/scripts/generate_assets.sh` and append the run metadata (command, commit, start/end timestamps, runtimes) to `docs/softwarex/assets/benchmark_runs.log`.
  - [x] Spot-check telemetry to ensure Tabu no longer reports implausible 0.09 s runtimes and that production/utilisation KPIs improve relative to previous assets.
  - [ ] Re-run \texttt{make manuscript-benchmarks} once more immediately before submission to capture the final artefact hash referenced in Section~4 (skip redundant runs mid-phase).
- [x] Convert refreshed benchmark/tuning data into manuscript-ready artifacts (Section 3).
  - [x] Build LaTeX tables for solver performance (Table~1) and tuning leaderboard (Table~2) by parsing the new `summary.csv` and `tuner_*.csv` files; store intermediates under `docs/softwarex/assets/data/tables/`.
  - [x] Regenerate Figure~2 (scaling curve) and Figure~3 (playback robustness) from the updated CSVs; ensure PNG/PDF exports meet 300 dpi and embed references in Section~\ref{sec:illustrative-example}.
  - [x] Update the narrative in Section~3 to quote the new objectives, runtimes, utilisation, and costing numbers, citing file paths for reproducibility.
- [x] Verify metadata tables/README alignment and document reproducibility log location for future edits (see `docs/softwarex/manuscript/README.md`).
- [x] Draft Section 4 (Impact/availability) while data context is fresh.
  - [x] Summarise adoption signals (GitHub stats, release cadence, documentation reach) and the BC validation roadmap.
  - [x] Reference forthcoming validation studies (Chapter 2 case studies) and explain how FHOPS enables them without duplicating results here.
  - [x] Tie the section back to reproducibility artefacts (Make targets/CLI flows, benchmark logs, dataset availability) so reviewers see the full traceability story.
- [x] Finalize reproducible asset documentation before the benchmark suite grows further.
  - [x] Expand `docs/softwarex/manuscript/README.md` with runtime expectations, environment variables (e.g., `FHOPS_ASSETS_FAST=1`), and troubleshooting tips for each script.
  - [x] Add a short manual checklist (until CI is ready) referencing the outputs each script must produce under `docs/softwarex/assets/`.
  - [x] Note telemetry/temporary files that stay ignored (e.g., `**/telemetry/steps/*.jsonl`) in the local `.gitignore` and confirm `submission_readiness_dashboard.md` points to the correct artifact directories.
- [x] Break phases into actionable GitHub issues with owners and deadlines.
  - [x] Translate each checkbox (or logical grouping) into issue(s) with clear scope (see Phase 0 timeline block above for the canonical mapping).
  - [x] Assign DRIs and add due dates/milestones to keep momentum (captured per-issue with dates aligned to FHOPS release gates).

## Links and Notes
- **Guide for Authors:** `docs/softwarex/reference/softwarex_guide_for_authors.html` (source: https://www.elsevier.com/journals/softwarex/2352-7110/guide-for-authors) – snapshot from Elsevier site for offline reference.
- **Elsevier LaTeX Template:** `docs/softwarex/reference/templates/elsarticle-template.zip` (source: https://www.elsevier.com/__data/assets/file/0011/56846/elsarticle-template.zip) – base template package (elsarticle) recommended by SoftwareX.
- **Top-Cited Crossref Snapshot:** `docs/softwarex/reference/softwarex_top_cited_crossref.json` – 25 most-cited SoftwareX articles pulled via Crossref API (sort=`is-referenced-by-count`).
- **Exemplar Library Notes:** `docs/softwarex/reference/examples/README.md` plus per-paper `metadata.md` files capture DOI/PII and readiness signals; PDFs now mirrored locally thanks to the manual download assist.
- **Exemplar Analysis Log:** `notes/softwarex_exemplar_analysis.md` distills structure/readiness cues from each paper so we can trace requirements back to concrete SoftwareX examples.
- **Submission Readiness Dashboard:** `notes/submission_readiness_dashboard.md` encodes the benchmark criteria and indicators reverse-engineered from the exemplar set.
- **Reference Vault README:** `docs/softwarex/reference/README.md` records provenance (retrieval dates, source URLs) for the instruction snapshots, templates, Crossref dump, and exemplar PDFs.
- **Thesis Alignment Notes:** `notes/thesis_alignment.md` (to be expanded) will map which FHOPS analyses stay in the SoftwareX paper vs. which BC case studies remain reserved for Rosalia Jaffray’s Chapter 2.

---

## FHOPS contribution focus (from Jaffray MASc review)
We leverage Rosalia’s Chapter 1 literature review to stay aligned with the real gaps in forest-harvest planning software. Summarised themes:
- **Open, reusable tooling:** Henkelman (1978), Weintraub & Bare (1996), Heinimann (2007), and later reviews show most models are one-off or closed. FHOPS’ scenario contract + solver + telemetry stack is our answer to this gap.
- **Integrated, multi-problem workflows & reproducibility:** Existing papers often tackle isolated sub-problems and rarely publish scripts/telemetry. FHOPS provides a unified workflow (scenario → optimisation → evaluation) with reproducible CLI/API entry points. This is the core SoftwareX contribution.
- **Real-world BC case studies:** Multiple BC-based deployments are still needed to answer the open questions Rosalia raised (e.g., how FHOPS behaves across ecological/operational contexts). FHOPS enables those studies, but we’ll reserve the detailed case-study content for her Chapter 2 so we don’t cannibalize her contributions.

Real-world case studies & validation – The literature (and Rosalia’s conclusion) stresses the need for multiple BC-based case studies (small-scale tenures, skyline vs. ground-based, salvage corridors, etc.) to validate models against real operational data and answer questions like “How does the framework perform across different ecological/operational contexts?” FHOPS only partially fills this today: we provide the tooling, default harvest-system registry, and reference datasets, but we haven’t published deep BC case-study analyses yet. That’s exactly the “easy win” Rosalia’s Chapter 2 will deliver—deploy FHOPS on two or three BC case studies to answer those open questions. For the SoftwareX submission, we should state that FHOPS enables those studies but reserve the detailed results for Rosalia’s thesis/papers.

So, alignment proposal:
- SoftwareX paper focuses on the open-source platform, reproducible workflow, and exemplar-level benchmarks (small synthetic runs demonstrating capability).
- Rosalia’s Chapter 2 (and any companion paper) retains the detailed BC case-study analysis (multi-case validation, policy insights, trade-off maps) so her thesis still delivers the “real-world deployment” contribution.

---

## FHOPS contribution focus (from Jaffray MASc review)
We leverage Rosalia’s Chapter 1 literature review to stay aligned with the real gaps in forest-harvest planning software. Summarised themes:
- **Open, reusable tooling:** Henkelman (1978), Weintraub & Bare (1996), Heinimann (2007), and later reviews show most models are one-off or closed. FHOPS’ scenario contract + solver + telemetry stack is our answer to this gap.
- **Integrated, multi-problem workflows & reproducibility:** Existing papers often tackle isolated sub-problems and rarely publish scripts/telemetry. FHOPS provides a unified workflow (scenario → optimisation → evaluation) with reproducible CLI/API entry points. This is the core SoftwareX contribution.
- **Real-world BC case studies:** Multiple BC-based deployments are still needed to answer the open questions Rosalia raised (e.g., how FHOPS behaves across ecological/operational contexts). FHOPS enables those studies, but we’ll reserve the detailed case-study content for her Chapter 2 so we don’t cannibalize her contributions.


Real-world case studies & validation – The literature (and Rosalia’s conclusion) stresses the need for multiple BC-based case studies (small-scale tenures, skyline vs. ground-based, salvage corridors, etc.) to validate models against real operational data and answer questions like “How does the framework perform across different ecological/operational contexts?” FHOPS only partially fills this today: we provide the tooling, default harvest-system registry, and reference datasets, but we haven’t published deep BC case-study analyses yet. That’s exactly the “easy win” Rosalia’s Chapter 2 will deliver—deploy FHOPS on two or three BC case studies to answer those open questions. For the SoftwareX submission, we should state that FHOPS enables those studies but reserve the detailed results for Rosalia’s thesis/papers.
So, alignment proposal:
SoftwareX paper focuses on the open-source platform, reproducible workflow, and exemplar-level benchmarks (small synthetic runs demonstrating capability).
Rosalia’s Chapter 2 (and any companion paper) retains the detailed BC case-study analysis (multi-case validation, policy insights, trade-off maps) so her thesis still delivers the “real-world deployment” contribution.
