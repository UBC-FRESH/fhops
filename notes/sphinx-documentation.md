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
[x] **Telemetry Ops Runbook** – `docs/howto/telemetry_ops.rst` now covers weekly notebook runs, telemetry maintenance, and Pages publication checklists (2025-11-22).
[x] **API Narrative Guides** – `docs/api/fhops.{scenario,optimization,evaluation}.rst` now include narrative intros + snippets covering Scenario→Problem usage, MIP builder entry points, and KPI evaluation (2025-11-22).
[x] **Release & Contribution Playbook** – `docs/howto/release_playbook.rst` now covers release prep, versioning, command suite, and PR expectations (2025-11-22).
[ ] **API Docstring Enhancements (feature/api-docstring-enhancements)** — add descriptive module/class/function docstrings across core packages to feed richer Sphinx API output.
    - [x] CLI modules: document command groups (`fhops.cli.main`, `benchmarks`, `dataset`, etc.) with purpose and usage hints *(2025-11-23: refreshed Typer command docstrings to include per-parameter details, telemetry semantics, and output notes).*
    - [x] Scenario contract & IO: describe key dataclasses (`Scenario`, `Problem`, `MobilisationConfig`, loaders) with field semantics, examples, and validation notes *(2025-11-23: Pydantic models now expose `Attributes` sections covering units/validation rules).*
    - [x] Optimisation layer: expand docstrings for `fhops.optimization.mip.builder`, drivers, and heuristics (SA/ILS/Tabu), outlining inputs, constraints, and returns *(2025-11-23: heuristic drivers now describe operator knobs, telemetry payloads, and return schemas).*
    - [x] Evaluation: provide detail for playback, KPI calculators, exporters (parameters, expected DataFrame schemas, sample usage).
    - [x] Productivity/reference modules: annotate public helpers with units, source references, and when to use each regression *(2025-11-23: forwarder, skidder, shovel logger, processor, cable logging, and helicopter helpers now mirror the CLI docs; remaining work limited to loaders/validators).* 
    - [x] Regenerate Sphinx API docs after docstrings are fleshed out; ensure `docs/api/*.rst` pulls the new content *(2025-11-24: `sphinx-build -b html docs _build/html -W` ran clean after the costing pass).*

### Outstanding docstring gaps (2025-11-23 deep-dive, updated 2025-11-24)
- **Productivity core**: `cable_logging.py` still lacks docstrings on internal validators (`_validate_inputs`, `_profile_slope_percent`, `_m3_per_pmh*`), helper selectors (`_running_skyline_variant`, `_helicopter_spec`), TR127 loader classes (`_TR127Predictor`, `_TR127Regression`, `_load_tr127_models`, `_ensure_tr127_inputs`, `_warn_if_out_of_range`), TN173 dataclass/loaders, and small helpers like `default_payload_kg` / `rated_payload_lb`. Export list already exposes these names via `__all__`, so autodoc shows blank slots.
- **Grapple presets**: `grapple_bc.py` has almost no docstring coverage across TN157/TN147/TR122/ADV5N28 metadata, `list_*_ids`, and productivity functions (`estimate_grapple_yarder_productivity_*`). These feed the CLI feller-buncher/manual-felling workflows.
- **Processor/loader suite**: `processor_loader.py` still missing docstrings for every dataset loader, dataclass, and helper (Berry/Labelle/ADV/TN/TR/loader cost estimates). This covers manual felling, processor costs, loader hot/cold modes, etc.
- **CTL/harvester forwarders**: `eriksson2014.py`, `ghaffariyan2019.py`, `harvester_ctl.py`, `forwarder_bc.py` internal helpers, and validators in `sessions2006.py` & `shovel_logger.py` still lack docstrings.
- **Skidder internals**: `_load_skidder_speed_profiles`, `_han2018_cycle_time_seconds`, `_segment_time` remain undocumented.
- **Costing layer**: ✅ `costing/inflation.py`, `costing/machine_rates.py`, and `costing/machines.py` now mirror the CLI detail level (NumPy docstrings, unit annotations, attributes, and parameter-by-parameter descriptions). Autodoc output confirmed via Sphinx build.

#### Docstring standards (2025-11-24 update)
- `CODING_AGENT.md` now spells out the NumPy-style expectations (summary + Parameters/Returns/Raises/Notes, attribute listings for dataclasses, usage of snippets, cross-link obligations, and requirement to run `sphinx-build -b html docs _build/html -W` after sweep).
- `CONTRIBUTING.md` mirrors the same guidance so external collaborators see the exact docstring contract (per-argument coverage, return schemas, citations, and build verification).

### Next docstring tasks
- [x] **Grapple BC module** – document TN157/TN147/TR122/ADV5N28 dataclasses, list/get helpers, and `estimate_grapple_yarder_productivity_*` functions (include units, source citations, payload defaults). Tack on docstrings for helper validators to avoid blank sections in autodoc. *(2025-11-24: Added Attributes sections for all dataclasses, detailed Parameters/Returns for list/get helpers and estimator functions, plus source notes for SR-54, TR-75, TN157/147, TR122, ADV5N28, ADV1N35, and ADV1N40. Sphinx build pending after full productivity sweep.)*
    - [x] Describe TN157/TN147/TR122/ADV5N28 metadata dataclasses (`Attributes` + sources/units).
    - [x] Add loader/helper docstrings (`list_*_ids`, `get_*`, `_validate_inputs`) describing return schemas.
    - [x] Expand `estimate_*` productivity helpers with parameter ranges, payload defaults, and KPI outputs, plus cite FPInnovations bulletins.
- [x] **Processor/loader module** – add top-level docstrings to dataset loaders, result dataclasses (Labelle, ADV, TN, TR sets), and CLI-facing estimators (processor/loader productivity + costing). Cover manual felling cost helpers, loader forwarder utilities, and Labelle polynomial entries. *(2025-11-24: Dataset loaders now explain their datasets, every exported dataclass exposes an `Attributes` section, and all estimator helpers—Berry/Labelle/Visser/Bertone/Borz/Nakagawa plus loader/clambunk utilities—include NumPy-style Parameters/Returns with validation notes and citations. Sphinx rebuild pending.)*
    - [x] Add module summary referencing Berry/Labelle datasets and CLI consumers. *(addressed via per-loader docstrings; module header already captures scope.)*
    - [x] Document every result dataclass (`Attributes`, units, dataset citation) plus dataset loader helpers. *(2025-11-24: Coverage now includes AutomaticBuckingAdjustment, Berry stats, carrier profiles, Labelle/TN/ADV/TR result payloads, loader results, and newly documented dataset loaders.)*
    - [x] Expand estimator docstrings with input validation rules, default multipliers, and return payload semantics. *(2025-11-24: All processor/loader estimators now describe inputs/returns; future changes should maintain the pattern.)*
- [ ] **Productivity core clean-up** – tackle cable logging validators, grapple presets, and CTL/forwarder helpers in one pass to eliminate the final blank autodoc sections; finish by re-running the Sphinx build noted above. *(2025-11-24 status: productivity helpers complete; remaining work moves to CLI/evaluation/heuristics per scan below.)*
    - [x] Document cable logging validators/selector helpers (TR127/TN173) and expose applicability notes *(2025-11-24: Added docstrings for `_validate_*`, `_running_skyline_variant`, `_helicopter_spec`, TR127 predictors/regressions/helpers, TN173 dataclasses/loaders, and helicopter payload utilities.)*
    - [x] Fill gaps in CTL/forwarder modules (`eriksson2014`, `ghaffariyan2019`, `sessions2006`, `skidder_ft`) plus skidder internals *(2025-11-24: Added Attributes/Parameters coverage for the Eriksson/Lindroos, Ghaffariyan, and Sessions shovel logging helpers, documented Han et al. skidder internals—including `_load_skidder_speed_profiles`, `_han2018_cycle_time_seconds`, `_segment_time`—and refreshed the grapple-skidder/forwarder docstrings.)*
    - [x] Re-run `sphinx-build -b html docs _build/html -W` and snapshot coverage deltas in this note *(2025-11-24: Build completed after CTL/skidder sweep; `_build/` removed.)*
    - [x] Document the BC forwarder helper (`forwarder_bc.py`) detaching the remaining autodoc gaps *(2025-11-24: Added Attributes/Parameters docstrings for `ForwarderBCResult`, `estimate_forwarder_productivity_bc`, and the ADV6N10 helper; reran Sphinx.)*

### New docstring gaps (AST scan 2025-11-24)
- **CLI dataset surface (`src/fhops/cli/dataset.py`)** – numerous enums/helpers lack docstrings (`ForwarderBCModel` derivatives, `_apply_*_defaults`, `_render_*` telemetry helpers, etc.), causing blank Sphinx entries and harder-to-read CLI help. Prioritise short descriptions + parameter hints for anything surfaced via `fhops dataset`.
- **CLI utilities (`cli/_utils.py`, `cli/benchmarks.py`, `cli/main.py`, `cli/profiles.py`, `cli/synthetic.py`, `cli/telemetry.py`)** – internal helpers and profiles enumerations remain undocumented (e.g., `_record_metrics`, `_collect_tuning_scenarios`, `_describe_metadata`), leaving the CLI reference sparse.
- **Evaluation playback (`src/fhops/evaluation/**/*`)** – dataclasses/functions inside `playback/stochastic.py`, `playback/adapters.py`, and `metrics/kpis.py` still lack docstrings (e.g., `PlaybackSample.apply`, `_system_metadata`), so Chapter 2 API docs omit parameter descriptions.
- **Optimization heuristics (`src/fhops/optimization/heuristics/*`)** – registry/ILS helpers (e.g., `OperatorRegistry.__init__`, `_local_search`, `_assignments_to_schedule`) remain undocumented despite being referenced in tuning docs.
- **Remaining productivity stragglers** – modules like `kellogg_bettinger1994.py`, `laitila2020.py`, `stoilov2021.py` still need NumPy-style docstrings even though their wrappers are covered.

### Next docstring tasks
- [ ] **CLI dataset module sweep** – add concise docstrings to exported enums, `_apply_*` default helpers, telemetry renderers, and validation utilities in `src/fhops/cli/dataset.py`.
    - [x] Enumerations covering ADV/TN/TR/Loader/Spinelli presets now describe their usage so CLI docs no longer show blank entries (2025-11-24).
    - [ ] Document the `_apply_*` default helpers, telemetry renderers, and validation utilities that back the CLI output.
- [ ] **CLI ancillary modules** – document `cli/_utils.py`, `cli/benchmarks.py`, `cli/main.py`, `cli/profiles.py`, `cli/synthetic.py`, and `cli/telemetry.py` helper functions/enums so the CLI API pages carry usable descriptions.
- [ ] **Evaluation playback/docs** – cover `evaluation/playback/stochastic.py`, `adapters.py`, and metrics dataclasses, focusing on parameter/return schemas referenced in thesis workflows.
- [ ] **Heuristics internals** – add docstrings to `optimization/heuristics/ils.py` and `heuristics/registry.py` classes/functions that appear in the tuning notes.
- [ ] **Productivity stragglers** – finish docstrings for `kellogg_bettinger1994.py`, `laitila2020.py`, `stoilov2021.py` (and any other remaining `productivity/*.py` files flagged by the scan).
