# Submission Readiness Dashboard

> Derived from exemplar SoftwareX papers: PyLESA, pycity_scheduling, cashocs, PyDDRBG, GROMACS, libxc, MOOSE, TSFEL, and the Advanced LIGO/Virgo open-data release. Every indicator below encodes an editor-facing benchmark we observed repeatedly. Track them with checkboxes so we cannot submit until all gates are satisfied.

## Dashboard Snapshot
| # | Dimension | Indicator | Target Before Submission | Exemplar Signals |
|---|-----------|-----------|--------------------------|------------------|
| 1 | Narrative & Metadata | Manuscript follows SoftwareX canonical order with populated metadata table + highlights + graphical abstract. | ✅ Final template review checklist signed off. | PyLESA, cashocs |
| 2 | Architecture Story | One-page architecture/workflow figure cross-linked to Sphinx overview + caption referencing FHOPS modules. | Figure exported in vector + raster formats, caption reviewed. | pycity_scheduling, MOOSE |
| 3 | Benchmark Coverage | Scenario/benchmark matrix covering ≥3 optimisation classes with reproducible configs + KPIs. | Benchmark manifest lives in repo + referenced in manuscript. | PyDDRBG, PyLESA |
| 4 | Reproducibility Pipeline | “How to reproduce” section mapping datasets, scripts, CI logs, and environment exports. | Dry-run reproduction completed on clean machine + hashes recorded. | PyDDRBG, cashocs, MOOSE |
| 5 | Artifact Packaging | Submission bundle w/ DOI-minted release, template cover letter, and artifact README mirroring LIGO-style instructions. | Zenodo/DOI link + checksum table stored in docs/softwarex/submissions/. | cashocs, LIGO |
| 6 | Performance Evidence | Tables/plots showing solver performance vs. baselines (runtime, quality, scalability). | Results scripts regenerate all figures in ≤1 command. | GROMACS, cashocs |
| 7 | Impact Metrics | Quantitative adoption evidence (users, installations, citations, integration partners). | Metrics table vetted by product + comms teams. | GROMACS, TSFEL |
| 8 | Governance & Contribution | Section outlining governance, release cadence, and contribution workflow consistent with repo docs. | Governance text synced with CONTRIBUTING.md / README. | libxc, MOOSE |
| 9 | Documentation Parity | Shared text blocks between manuscript + Sphinx overview using includes/snippets to avoid drift. | Include tests run; Sphinx build proves reuse. | TSFEL |
|10 | Submission Logistics | All SoftwareX portal steps rehearsed (forms, highlights, ORCID, funding statements). | Checklist artifact checked in + dry-run timestamped. | PyLESA, journal instructions |

## Detailed Indicators & Tasks

### 1. Narrative & Metadata Compliance
- [ ] Apply Elsevier `elsarticle` template with SoftwareX class + metadata tables populated (Software Metadata, Current Code Version, etc.).
  - Measurement: Template diff reviewed vs. official instructions PDF.
  - Evidence sources: PyLESA & cashocs show full compliance including highlights + graphical abstract.
- [ ] Draft 3 highlights + 1-sentence impact summary aligned with FHOPS differentiators.
- **Exemplar refs:** PyLESA pp. 1–2 for gap framing + metadata tables; cashocs §2 for structured “software update” narrative.

### 2. Architecture & Workflow Visualization
- [ ] Produce a single source-of-truth diagram (vector + PNG) explaining FHOPS architecture, optimisation workflow, and integration with docs.
  - [x] PRISMA-style LaTeX source wired into the manuscript (`sections/includes/prisma_overview.tex`) and referenced in Section~2.
  - [x] Narrative include wired into Sphinx Overview via `docs/includes/softwarex/prisma_overview.rst`.
  - [ ] PNG/SVG export workflow scripted so Sphinx can display the same visual asset.
- [ ] Validate figure readability at journal column width (per SoftwareX instructions).
- **Exemplar refs:** PyLESA Fig. 1 (pp. 2–3), pycity_scheduling Fig. 1 (coordination approach), MOOSE §1 architecture narrative.

### 3. Benchmark & Scenario Matrix
- [ ] Define ≥3 benchmark families (e.g., scheduling, routing, resource allocation) with KPIs and datasets.
- [ ] Store configs + seeds under version control; include manifest table mirroring PyDDRBG.
- [ ] Generate auto-plotted tables/plots tying FHOPS heuristics to baseline solvers.
- **Exemplar refs:** PyDDRBG §2 (benchmark generator + robust mean peak ratio), PyLESA §3 (district-heating sizing KPI plots).

### 4. Reproducibility & Automation
- [ ] Create `make manuscript-benchmarks` (or hatch task) that reruns all experiments; log hashes + runtimes.
- [ ] Capture environment export (conda/pip + container digest) and store under docs/softwarex/reference/.
- [ ] Add CI badge / log snippet proving at least one clean reproduction run (MOOSE-style evidence).
- **Exemplar refs:** PyDDRBG §2.3 (evaluation metrics + scripts), cashocs §2 (release notes + automation), MOOSE §1 (parallel execution guarantees).

### 5. Artifact Packaging & DOI
- [ ] Register Zenodo concept DOI and map to FHOPS release targeted for submission.
- [ ] Prepare artifact README with onboarding, requirements, checksum table (LIGO example).
- [ ] Bundle sample data + notebooks referenced in manuscript.
- **Exemplar refs:** Advanced LIGO/Virgo Open Data §§3–4 (data products + access instructions), cashocs release notes (versioning).

### 6. Performance & Accuracy Evidence
- [ ] Produce scaling chart (problem size vs. runtime/quality) akin to GROMACS appendices.
- [ ] Include comparative table (FHOPS vs. baseline heuristics or commercial solvers) with statistical significance notes.
- [ ] Script exports camera-ready CSV/LaTeX tables.
- **Exemplar refs:** GROMACS §3 (multi-level parallelism + performance tables), cashocs §3 (topology optimisation benchmarks).

### 7. Impact & Adoption Signals
- [ ] Collect metrics: GitHub stars/forks, downloads, number of organisations in pilot, citations (if any), internal deployment stats.
- [ ] Craft “Impact” section referencing real-world projects, similar to TSFEL/GROMACS narratives.
- [ ] Secure approvals for disclosing partner names if applicable.
- **Exemplar refs:** GROMACS abstract + §4 (adoption metrics), TSFEL abstract (user entry points) for tone.

### 8. Governance & Contribution Workflow
- [ ] Document governance model (core maintainers, review SLAs, release cadence) mirroring libxc/MOOSE.
- [ ] Ensure CONTRIBUTING.md + CODEOWNERS align with manuscript description.
- [ ] Mention automated QA (lint/tests) and community processes (issue triage, RFCs).
- **Exemplar refs:** libxc §1 (cross-community maintenance), MOOSE §1 (sharing + composability).

### 9. Documentation Parity & Content Reuse
- [ ] Identify shared text blocks (Overview, feature list, workflow description) and move them into shared include files.
- [ ] Wire Sphinx build to import those includes; verify formatting.
- [ ] Add regression test (maybe `tox -e docs-shared`) to detect drift.
- **Exemplar refs:** TSFEL §2 (API + GUI dual entry) shows how to share documentation narrative; pycity_scheduling doc references tie CLI + docs together.

### 10. Submission Logistics & Portal Rehearsal
- [ ] Populate SoftwareX cover letter + highlights template; store under `docs/softwarex/submissions/`.
- [ ] Verify ORCID/funding/acknowledgement data for all authors.
- [ ] Dry-run portal inputs (screenshots or checklist) and log any blockers.
- **Exemplar refs:** PyLESA highlights layout; Guide for Authors submission checklist (portal steps).

## Status Tracking
- Track progress by checking boxes above and mirroring high-level status in `notes/softwarex_manuscript_plan.md` Phase 0/1/2 items.
- Add evidence links (commits, artifacts, figures) as each indicator flips to ✅.
