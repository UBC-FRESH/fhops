# Sphinx Documentation Audit

Date: 2025-11-22  
Status: Draft – captures current coverage and gaps ahead of Phase 4 release prep.

## Overview

FHOPS’ Sphinx tree lives under `docs/` and is published to Read the Docs via `.readthedocs.yaml`. The current structure includes:

| Section | Path(s) | Coverage Notes |
| --- | --- | --- |
| Landing & Navigation | `docs/index.rst` | Links to overview, quickstart, how-tos, API, CLI reference, and analytics notebooks. |
| Overview | `docs/overview.rst` | High-level intro + “Baseline Workflows” section referencing minitoy/regression fixtures and roadmap alignment. |
| Quickstart | `docs/howto/quickstart.rst` | End-to-end minitoy walkthrough (validate → solve-mip/heur → evaluate) plus regression baseline KPI table. |
| Data Contract | `docs/howto/data_contract.rst` | Schema tables, CSV/YAML descriptions, validation workflow, GeoJSON ingestion guide, sample fixtures. |
| Mobilisation & Geo | `docs/howto/mobilisation_geo.rst` | GeoJSON ingestion, `fhops geo distances`, mobilisation config examples, KPI interpretation. |
| Benchmarks | `docs/howto/benchmarks.rst` | Harness usage, options, output interpretation, plotting helper. |
| Evaluation | `docs/howto/evaluation.rst` | Deterministic playback, shift/day exports, KPI bundles, stochastic sampling hooks. |
| Telemetry & Tuning | `docs/howto/telemetry_tuning.rst` | CLI references for telemetry store, tuning commands (grid/random/bayes), dashboard usage. |
| CLI Reference | `docs/reference/cli.rst` | Command matrix for `fhops` CLI (solve, bench, geo, dataset, telemetry, synth). |
| Harvest Systems & Productivity | `docs/reference/harvest_systems.rst` | System registry, productivity helper references, costing tables, FPInnovations datasets. |
| API Reference | `docs/api/index.rst` + per-package stubs (`docs/api/fhops.*.rst`) | Autodoc coverage for scenario, scheduling, optimisation, evaluation modules. |
| ReadTheDocs Config | `.readthedocs.yaml` + `docs/requirements.txt` | Installs runtime deps; autodoc mocks only heavyweight libs (geopandas/highspy). |
| Examples/Notebooks | `docs/examples/analytics/` (rendered via nbconvert) | KPI deep-dive + stochastic analysis notebooks referenced from index. |

## Coverage by Theme

### Scenario Authoring
- **Docs:** `docs/howto/data_contract.rst`, README quickstart section, CLI reference (`fhops validate` examples), dataset inspection plan.
- **Status:** Comprehensive for CSV/YAML schema, GeoJSON, mobilisation integration. Includes minimal/typical/invalid fixtures under `tests/data/`.
- **Gaps:** Need explicit shift-template examples and road_construction table schemas for new users.

### Solvers & Benchmarks
- **Docs:** Quickstart, benchmarks how-to, CLI reference `fhops solve-*` sections, README quickstart, `docs/api/fhops.optimization.*`.
- **Status:** CLI usage documented; benchmark harness has interpretation guide + plotting helper.
- **Gaps:** Limited detail on SA operator registry, Tabu/ILS parameter tuning, and large-scale scenario pain points (runtime tips, parallel settings).

### Mobilisation & Geospatial
- **Docs:** Mobilisation how-to, data contract GeoJSON appendix, CLI reference (geo helper + solve flags).
- **Status:** Includes distance generation workflow, per-machine KPI explanations, sample CSVs.
- **Gaps:** No dedicated troubleshooting (CRS mismatches, zero-distance warnings) and no med42/large84 worked example narrative.

### Harvest Systems, Productivity, Costs
- **Docs:** Harvest systems reference, dataset CLI docs, roadmap notes cross-referenced.
- **Status:** Rich tables referencing FPInnovations studies, CLI commands for presets/helpers.
- **Gaps:** Cross-linking between harvest-system IDs referenced in sample scenarios and guide tables could be clearer.

### Evaluation & KPIs
- **Docs:** Evaluation how-to, telemetry/tuning guide, CLI reference (`fhops evaluate`, `fhops telemetry report`), notebooks.
- **Status:** Shift/day exports, KPI definitions, stochastic sampling API described; CLI examples included.
- **Gaps:** Need explicit “how to compare FHOPS results vs thesis Chapter 1 KPIs” guidance, plus tutorial on interpreting sequencing violation breakdowns.

### Telemetry & Tuning
- **Docs:** Telemetry how-to, CLI reference for tuning commands, dashboards described in README.
- **Status:** Covers random/grid/Bayesian tuner usage, telemetry schema, GitHub Pages build steps.
- **Gaps:** Pending instructions for the planned weekly notebook run, and no troubleshooting section for SQLite store lock/contention.

### API Reference
- **Docs:** Autodoc pages exist for core packages.
- **Status:** RTD builds succeed, but narrative context is minimal (mostly generated member listings).
- **Gaps:** Need curated module guides (e.g., “Using fhops.optimization.mip.builder” with example code) and cross-links to how-tos.

### Release & Contribution
- **Docs:** CONTRIBUTING.md, CODE_OF_CONDUCT.md, README mentions planning artefacts.
- **Status:** Base expectations documented, but Phase 4 release checklist still in notes.
- **Gaps:** No Sphinx-based contributor guide, no release playbook page, PR template coverage missing from docs.

## TODO – Weak or Missing Coverage

[x] **Shift Templates & Road Tables** – `docs/howto/data_contract.rst` now documents multi-shift calendars, validation via `fhops validate`, and the `road_construction` CSV schema plus CLI guidance (2025-11-22).
[x] **Heuristic Operator Registry Guide** – `docs/howto/heuristic_presets.rst` now covers SA/ILS/Tabu parameter knobs, preset comparisons, and `operators_stats` usage (2025-11-22).
[x] **Mobilisation Troubleshooting** – `docs/howto/mobilisation_geo.rst` now documents CRS warnings, zero-distance diagnostics, and med42/large84 walkthroughs with KPI interpretation (2025-11-22).
[x] **Harvest System Cross-Links** – `docs/reference/harvest_systems.rst` now includes a scenario map, and the med42/large84/synthetic READMEs explain how to tie blocks back to the registry (2025-11-22).
[x] **Thesis-Oriented Evaluation Tutorial** – `docs/howto/thesis_eval.rst` now walks through Chapter 2 case-study prep (validation, solver runs, KPIs, trade-off reporting) aligned with the Jaffray MASc proposal (2025-11-22).
[ ] **Telemetry Ops Runbook** – Document the upcoming weekly notebook workflow, telemetry storage maintenance (rotation, lock handling), and GitHub Pages verification steps.
[ ] **API Narrative Guides** – Supplement autodoc pages with short prose sections and code snippets for key modules (scenario contract, MIP builder, playback API).
[ ] **Release & Contribution Playbook** – Add a Sphinx page summarizing release steps (docs build, version bumps, changelog policy, PR templates) before Phase 4 public release.
