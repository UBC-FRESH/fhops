# SoftwareX Manuscript Rollout Plan

> **Planning Note:** Every task must use checkboxes and include subtasks/sub-subtasks as needed. Keep expanding items in-place as execution details emerge so we stay consistent with this structure.

## Goals
- [ ] Author a SoftwareX manuscript that showcases FHOPS and complements the existing Sphinx user guide (especially the Overview section).
  - [ ] Distill the narrative arc (problem, contribution, impact) tailored for SoftwareX readership.
  - [ ] Identify sections that can be shared with or reused inside the Sphinx Overview for consistency.
  - [ ] Capture reviewer-ready figures/tables list aligned with FHOPS differentiators.
- [ ] Create a reusable `docs/softwarex/` subfolder that can eventually surface key manuscript content in the broader documentation set.
  - [x] Define the subfolder layout (manuscript, reference, assets, submissions, automation).
  - [x] Wire up scripts or Make targets for building/checking manuscript assets.
  - [ ] Document contribution guidelines for manuscript files inside README.
- [ ] Follow SoftwareX author instructions precisely and benchmark readiness using exemplar publications.
  - [ ] Track the authoritative author guidelines version/date in repository metadata.
  - [ ] Maintain a checklist derived from instructions for ongoing compliance.
  - [x] Log insights/benchmarks from exemplar papers to inform quality gates.

## Phase 0 – Planning (Now)
- [ ] Capture requirements: Download the latest SoftwareX author instructions (PDF + any LaTeX/Word templates) into `docs/softwarex/reference/` and version them.
  - [x] Confirm the most recent instruction set from Elsevier/SoftwareX site.
  - [x] Download PDF instructions plus LaTeX/Word templates.
  - [x] Store raw artifacts under `docs/softwarex/reference/` with README describing provenance.
  - [x] Add version/date annotations to help track updates over time.
- [x] Build reference library: Collect 3–5 high-quality SoftwareX FH/optimization papers (PDF + citation metadata) inside `docs/softwarex/reference/examples/` with comparison notes.
  - [x] Curate candidate exemplar papers relevant to optimization frameworks.
  - [x] Download PDFs and save citation metadata (BibTeX/DOI) alongside each example.
  - [x] Write short benchmarking notes (strengths, structure cues, submission requirements) per exemplar.
- [ ] Align scope: Define manuscript success criteria, key story beats, figures/tables to reuse from docs, and how content will feed into Sphinx Overview.
  - [ ] Draft success criteria (acceptance goals, technical coverage, evaluation depth).
  - [ ] List candidate figures/tables pulled from existing docs or experiments.
  - [ ] Map each manuscript section to overlapping Sphinx content to avoid duplication.
- [ ] Decide workflow tooling: Choose manuscript format (LaTeX vs. Markdown-to-PDF pipeline), bibliography management, and automation hooks (e.g., `make manuscript`).
  - [ ] Evaluate tooling options (LaTeX template vs. MyST/pandoc flow) against SoftwareX requirements.
  - [ ] Select bibliography tooling (BibTeX, Zotero export, etc.) and storage location.
  - [ ] Define automation commands/scripts for building and linting manuscript artifacts.
- [ ] Establish timeline & ownership: Turn phases into GitHub issues/milestones, map DRI(s), and set review checkpoints that align with FHOPS releases.
  - [ ] Convert each phase into one or more GitHub issues with owners/due dates.
  - [ ] Align manuscript milestones with FHOPS release cadence.
  - [ ] Schedule recurring review checkpoints (internal review, doc sync, artifact verification).

## Phase 1 – Manuscript Architecture & Repo Scaffolding
- [ ] Stand up `docs/softwarex/manuscript/` with template files (main manuscript, supplementary material, metadata).
  - [x] Copy the selected SoftwareX template into the repo structure.
  - [ ] Prepare placeholders for supplementary files and metadata tables.
  - [x] Add README describing how to compile and where outputs land.
- [ ] Create a section-by-section outline that mirrors SoftwareX structure (Abstract, Software Metadata, etc.) and cross-reference planned FHOPS documentation tie-ins.
  - [ ] List required sections per SoftwareX guidelines.
  - [ ] For each section, note primary FHOPS content sources (code, docs, experiments).
  - [ ] Highlight sections that need coordination with Sphinx to reuse text.
- [ ] Draft a mapping document showing what portions can be shared with Sphinx (e.g., Overview narrative, feature tables).
  - [ ] Identify overlapping narrative components.
  - [ ] Decide on shared include files or content fragments.
  - [ ] Document synchronization process between manuscript and Sphinx.
- [ ] Establish build scripts/notebooks for regenerating figures, tables, and performance benchmarks referenced in the paper.
  - [ ] Inventory required figures/tables and their data sources.
  - [ ] Create reproducible scripts/notebooks to regenerate each artifact.
  - [ ] Integrate artifact generation into CI or a manual checklist.

## Phase 2 – Content Drafting
- [ ] Produce first-pass text for each major section, incorporating FHOPS capabilities, unique contributions, and methodology.
  - [ ] Draft Abstract, Intro, and Software Metadata sections.
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
- [x] Add author instruction PDFs/templates and exemplar papers to the repo.
  - [x] Populate `docs/softwarex/reference/` with guideline/template files.
  - [x] Save exemplar PDFs plus notes in `docs/softwarex/reference/examples/`.
- [ ] Flesh out the manuscript outline + repo scaffolding under `docs/softwarex/`.
  - [x] Create directory skeleton and placeholder files per Phase 1.
  - [x] Draft outline document referencing SoftwareX sections.
- [ ] Break phases into actionable GitHub issues with owners and deadlines.
  - [ ] Translate each checkbox (or logical grouping) into issue(s) with clear scope.
  - [ ] Assign DRIs and add due dates/milestones to keep momentum.

## Links and Notes
- **Guide for Authors:** `docs/softwarex/reference/softwarex_guide_for_authors.html` (source: https://www.elsevier.com/journals/softwarex/2352-7110/guide-for-authors) – snapshot from Elsevier site for offline reference.
- **Elsevier LaTeX Template:** `docs/softwarex/reference/templates/elsarticle-template.zip` (source: https://www.elsevier.com/__data/assets/file/0011/56846/elsarticle-template.zip) – base template package (elsarticle) recommended by SoftwareX.
- **Top-Cited Crossref Snapshot:** `docs/softwarex/reference/softwarex_top_cited_crossref.json` – 25 most-cited SoftwareX articles pulled via Crossref API (sort=`is-referenced-by-count`).
- **Exemplar Library Notes:** `docs/softwarex/reference/examples/README.md` plus per-paper `metadata.md` files capture DOI/PII and readiness signals; PDFs now mirrored locally thanks to the manual download assist.
- **Exemplar Analysis Log:** `notes/softwarex_exemplar_analysis.md` distills structure/readiness cues from each paper so we can trace requirements back to concrete SoftwareX examples.
- **Submission Readiness Dashboard:** `notes/submission_readiness_dashboard.md` encodes the benchmark criteria and indicators reverse-engineered from the exemplar set.
- **Reference Vault README:** `docs/softwarex/reference/README.md` records provenance (retrieval dates, source URLs) for the instruction snapshots, templates, Crossref dump, and exemplar PDFs.
