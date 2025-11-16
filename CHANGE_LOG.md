# Development Change Log

# Development Change Log

## 2025-11-18 — Machine-rate CLI + repair allowances
- Wired the FPInnovations repair/maintenance multipliers into the costing workflow: `fhops.costing.machine_rates.compose_rental_rate()` now builds rental rates (owning + operating + optional repair) with override hooks, and `MachineCostEstimate` / helpers retain the per-component breakdown for downstream consumers.
- Extracted the Advantage Vol. 4 No. 23 usage-class multipliers for each curated role (5k–25k SMH buckets) and stored them alongside the $/SMH defaults in `data/machine_rates.json`; the loader now exposes the normalized multipliers so costing tools can scale repair allowances for alternate machine ages. Added regression coverage in `tests/test_costing.py`.
- `fhops.costing.machine_rates.compose_rental_rate()` and `fhops.dataset estimate-cost` accept an optional `usage_hours` argument/flag to pick the closest FPInnovations bucket, so specifying `--usage-hours 5000` now scales the repair allowance automatically (table output shows the bucket + multiplier applied).
- Scenario machines gained an optional `repair_usage_hours` column so datasets can request younger/older repair allowances during validation; the synthetic/scenario loaders now pass the hint into the machine-rate defaults and tests cover the behavior. Docs/planning updated accordingly, `fhops.dataset estimate-cost` can now ingest `--dataset/--machine` to auto-fill role/usage (no more manual `--machine-role`/`--usage-hours` for report scripts), and `fhops.dataset inspect-machine` prints the implied owning/operating/repair breakdown (with `--json-out` support for automation) for quick QA.
- Telemetry now snapshots machine-rate assumptions: `solve-heur`, `solve-ils`, `solve-tabu`, and `eval-playback` attach the same machine cost payload emitted by `inspect-machine --json-out` (owning/operating/repair split + usage buckets) so KPI dashboards and tuner histories can trace which FPInnovations buckets were assumed for each run. `fhops telemetry report` and `scripts/analyze_tuner_reports.py` expose the `machine_costs_summary` column so downstream analytics can group/compare cost assumptions over time.
- KPI summaries emit a `repair_usage_alert` warning when any machine uses a non-default FPInnovations usage bucket (≠10 000 h), and telemetry reports/analytics propagate the alert so dashboards and badges can highlight those runs automatically.
- Extended `fhops.dataset estimate-cost` so users can specify `--machine-role` instead of a raw rate; the command loads the role’s defaults from `data/machine_rates.json`, applies overrides (`--owning-rate`, `--operating-rate`, `--repair-rate`), toggles the FPInnovations allowance, and prints the source plus breakdown. Added regression tests in `tests/test_costing.py` to cover the new helper.
- Documented the CPI assumption and CLI workflow in `notes/dataset_inspection_plan.md`, and queued the documentation/system-integration follow-ups in the planning section.
- Expanded `docs/howto/data_contract.rst` with a “Machine-Rate Defaults & Costing Helper” section covering the CAD assumptions, FPInnovations 1.56 CPI escalation, and CLI usage examples so dataset authors know how to consume the defaults.
- Scenario contract + synthetic datasets now auto-fill machine rental rates from the role defaults: `Machine` models backfill `operating_cost` when set to `0`, the synthetic generator writes roles + rates (using the rental table), and all example `machines.csv` templates now include canonical role slugs for downstream costing. The dataset guide notes the new fallback.
- Added Lee et al. (2018) HAM300 skyline helper to `fhops.productivity.cable_logging`, exposing uphill/downhill productivity regressions (cycle time vs. yarding/lateral distance and large-end diameter) with defaults matching the case study payloads; new tests in `tests/test_cable_logging.py` cover the expected m³/PMH outputs.
- Normalised machine-role strings across the scenario loader, synthetic generator, and harvest-system constraints: roles now canonicalise to snake_case slug names (e.g., `feller-buncher` → `feller_buncher`, `roadside processor` → `processor`), backed by the machine-rate lookup. `normalize_machine_role` is exported for downstream tools, solver constraints accept either naming style, and tests cover the new behaviour.
- Integrated Arnvik Appendix 5 stand metadata with the skyline helpers: added `fhops.reference.arnvik_appendix5` loader, CLI commands (`appendix5-stands`, `estimate-cable-skidding`) to inspect/consume the dataset, and new profile-aware Ünver-Okan helpers that pull slope defaults directly from the stand library. Tests cover slope parsing and profile-based regressions.
- Extended `fhops.dataset estimate-forwarder-productivity` so the ALPACA equations from Ghaffariyan et al. (2019) pick slope multipliers automatically via a new `--slope-class` flag (<10 %, 10–20 %, >20 %). Analysts can still override with `--slope-factor`, and `tests/test_cli_dataset_forwarder.py` verifies the CLI output matches the published curves.
- Imported the Lee (2018) and TR-125 skyline helpers into the dataset CLI so `fhops.dataset estimate-skyline-productivity` is lint-clean; added `tests/test_cli_dataset_skyline.py` to exercise both models end-to-end.
- Removed unused `_machine_cost_snapshot` assignments from `fhops.cli.main` commands that weren’t logging telemetry (`validate`, `build-mip`, `solve-mip`, `evaluate`) and cleaned up the dangling `primary_index` helper in `fhops.reference.arnvik_appendix5` to keep Ruff quiet.
- Tightened mypy coverage: scenario loader now coerces CSV values before range validation, the telemetry report renderer stringifies every column, and the machine-cost CLI enforces non-null forwarder/Kellogg inputs plus splits deterministic vs. RV productivity helpers so optional floats and mixed productivity types no longer trip type checking.
- Added TR-125 skyline regressions (single/multi-span) and TR-119 partial-cut treatment multipliers: skyline CLI now exposes `estimate-skyline-productivity` with optional `--tr119-treatment` scaling, productivity module exports the new helpers, and TR-119 data lives in `notes/reference/fpinnovations/tr119_yarding_productivity.json` for costing defaults. Tests cover the new loaders and regressions.

## 2025-11-17 — BC grapple yarder productivity helpers
- Added `fhops.productivity.grapple_bc` implementing MacDonald (1988) SR-54 (Washington 118A on mechanically bunched second-growth) and Peterson (1987) TR-75 (Madill 084 on bunched vs. hand-felled turns) travel-time models so FHOPS can estimate grapple yarder productivity using BC datasets instead of plantation regressions.
- Exported the new helpers via `fhops.productivity.__init__` and introduced unit coverage (`tests/test_productivity_grapple_bc.py`) that checks the regressions against the FERIC tables/figures and validates input semantics.
- Updated `notes/dataset_inspection_plan.md` to record the implementation and next steps (wiring models into the registry/cost helper, mining TR112/TR127 skyline data).
- Added University of British Columbia cable skidding helpers (`fhops.productivity.cable_logging`) based on Ünver-Okan (2020) regression equations (SPSS and robust variants) so the registry has a skyline/winch baseline until the TR112/TR127 coefficients are recovered. Exposed the functions via the productivity package and unit-tested the expected numeric outputs.
- Expanded the Arnvik (2024) Appendix 4 extract/normalizer: widened the Camelot region (landscape pages) and now capture the "Time recorded" + "Operation" columns, parse the combined `HM M` field into harvest/machine type, and emit `time_recorded` / `operation` metadata in `appendix4_machines_normalized.json`. Appendix 5 was re-extracted with the same region for consistency.

## 2025-11-16 — Brushwood harwarder productivity helper
- Implemented the Laitila & Väätäinen (2020) brushwood harwarder equations (`fhops.productivity.laitila2020`) so the CLI/registry can model roadside biomass recovery productivity given tree density, piece size, and forwarding distance.
- Added regression tests reproducing the paper’s reported 6.5–8.4 m³/PMH cases to guard the helper against future refactors.
- Logged the new helper + follow-on machine-role rollout plan in `notes/dataset_inspection_plan.md` and extracted the source PDF text into `notes/reference/article10379.txt` for future parsers.
- Extended forwarder coverage with Ghaffariyan et al. (2019) thinning models (small/large ALPACA regressions) and Kellogg & Bettinger (1994) multi-product CTL regression, complete with slope toggles, distance-aware predictors, regression tests, and reference text dumps under `notes/reference/`.
- Added `fhops dataset estimate-forwarder-productivity` so users can evaluate the new forwarder regressions from the CLI (Ghaffariyan small/large + Kellogg saw/pulp/mixed), with validation of required parameters and Typer-backed regression tests.
- Logged new planning references: Visser et al. (2025) mechanical grapple-feeding excavators, McNeel (2000) longline yarding, West et al. (2022) steep-slope winch-assist systems, Bell (2017) OpCost model thesis, Renzie (2006) partial-cut productivity, and Onuma (1988) NA time-study methodology, plus flagging the DRM-locked silviculture report for follow-up.
- Ported the Sessions & Boston (2006) shovel-logging cost/productivity formulation and the Spinelli et al. (2017) grapple yarder regression into reusable helpers (`fhops.productivity.sessions2006` / `spinelli2017`) with unit coverage, so Step 3 work can build on working code while we continue hunting for the Han & George data.

## 2025-11-15 — Dataset inspector & 24 h baseline
- Added a new `fhops dataset` CLI app with `inspect-machine` / `inspect-block` commands, interactive selectors, Rich table output, and warnings whenever a machine advertises non‑24 h availability so dataset regressions surface immediately.
- Enforced the 24 h/day contract across the stack: `Machine.daily_hours` now defaults to 24, all bundled `machines.csv` files were refreshed, and the synthetic generator exposes a `machine_daily_hours` override (also wired through the CLI/batch helpers).
- Updated docs/release notes to explain the round-the-clock assumption, the new inspector warning, and the synthetic CLI override so users know how to customise availability when required.

## 2025-11-14 — Tooling polish & CI compliance
- Added per-file Ruff ignores for the analytics notebooks so their sys.path bootstrapping cells stop tripping `E402`, and let `pre-commit` keep them formatted without destructive rewrites (`pyproject.toml`).
- Tightened the global typing story: telemetry/benchmark helpers now use modern unions, convergence reporting avoids `type: ignore`, and parquet exporters no longer rely on unused type ignores.
- Refined the tuning benchmark runner (`scripts/run_tuning_benchmarks.py`) with proper helper functions (no lambda assignments) and saner typing, and made the analyzer resilient when stitching best-objective stats together.
- GitHub Pages now converts the Markdown telemetry tables to standalone HTML (via Pandoc) and the docs link to those HTML renderings so the dashboards display as formatted tables instead of raw pipes.
- Added a scheduled workflow (`analytics-notebooks.yml`) that runs the full analytics notebook suite every Monday, captures timestamped artefacts, redeploys GitHub Pages with the refreshed dashboards, and documents the cadence in the telemetry how-to so stochastic regressions surface even when daily CI uses the light mode.
- Wrapped up the telemetry dashboards bundle: README + telemetry reference now point to `reference/dashboards`, dashboards embed the new history delta view, both CI workflows publish the delta artefacts, and the operations note captures the weekly workflow ownership/triage playbook.
- Scoped the `mypy` pre-commit hook to `src/`, disabled filename passing, and taught it to ignore third-party imports so the hook behaves like our documented `mypy src` workflow. Hook failures now flag missing CHANGE_LOG entries earlier.
- Regenerated the analytics notebook metadata with a trailing newline so the `end-of-file-fixer` hook no longer churns during CI.
- Refreshed `.pre-commit-config.yaml` (ruff v0.14.5, mypy v1.18.2, pre-commit-hooks v6.0.0) to eliminate the deprecated stage warning and keep local hooks aligned with upstream behavior.
- Started the release candidate prep effort on branch `release-candidate-prep`: added
  `notes/release_candidate_prep.md`, updated the roadmap detailed next steps, and expanded
  `CODING_AGENT.md` with Hatch-based release workflow guidance.
- Added `hatch.toml` with dev/release environments mirroring the CI cadence, ran `hatch build`
  to produce sdist/wheel artifacts, and smoke-tested the wheel in a fresh virtualenv via
  `fhops --help` and a minitoy validation run.
- Switched project versioning to Hatch’s dynamic mode (`pyproject.toml` derives from
  `src/fhops/__init__.__version__`), documented the bump workflow in `CODING_AGENT.md`, and
  refreshed README/docs with pip/Hatch install instructions plus a draft of the RC release notes.
- Ran the release candidate tuning sweep (`scripts/run_tuning_benchmarks.py --plan baseline-smoke`)
  and captured tuned vs. baseline improvements (`notes/release_tuning_results.md`). Best operator
  configurations per scenario/algorithm now live in `notes/release_tuned_presets.json` for reuse.
- Added `.github/workflows/release-build.yml`, which runs `hatch run release:build` on tag pushes
  and uploads the `dist/` artifacts; release instructions in `CODING_AGENT.md` now reference the
  automation. Added workflow comments clarifying that publishing still happens via manual twine
  steps documented in the release notes.
- Documented TestPyPI/PyPI publishing cadence (hatch build + twine upload + smoke install) in
  `notes/release_candidate_prep.md` and `CODING_AGENT.md`.
- Completed TestPyPI dry run: uploaded `fhops 0.0.2` via Hatch (`HATCH_INDEX=testpypi hatch publish`) and
  verified install in a fresh venv using `pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple fhops`.
- Release docs now describe the Hatch-only publish flow (no manual Twine invocation).
- CONTRIBUTING.md now references Hatch workflows (`hatch run dev:suite`, `hatch publish`) so
  contributors follow the same release process outlined in CODING_AGENT.md.
- Bumped package version to `0.1.0` in `src/fhops/__init__.py` ahead of the PyPI publish/tag.
- Added quick-demo commands (tuning harness runs) to README/docs overview and highlighted tuned
  presets in the release notes draft.

## 2025-11-13 — Docs landing fix
- Repaired `docs/index.rst` so the dashboards reference appears inside the “Getting Started” toctree, restoring a valid Sphinx build and keeping the telemetry links visible on GitHub Pages.
- Added the missing trailing newline to the generated analytics metadata JSON files so the `end-of-file-fixer` hook and CI stop rewriting them on every run.

## 2025-11-12 — Tuning bundles & delta polish
- Added bundle resolution helpers (`--bundle` / `-b`) to `fhops tune-random`, `fhops tune-grid`, and `fhops tune-bayes`, supporting built-in aliases (`baseline`, `synthetic[-tier]`, etc.) and custom manifests via `alias=/path/to/metadata.yaml`.
- Telemetry context now records `bundle` / `bundle_member`, and `tuner_summary.scenario_best` uses `bundle:member` keys so comparison scripts retain bundle provenance while generating reports/deltas.
- Documented bundle usage in `docs/howto/telemetry_tuning.rst`, updated the README, and marked the roadmap/plan checklist item (“Provide CLI surfaces for bundle sweeps”) as complete.
- Extended `scripts/analyze_tuner_reports.py` with per-scenario summary outputs (`--out-summary-csv`, `--out-summary-markdown`) so CI can surface the leading algorithm/objective per report without opening the full comparison table.
- Added ``scripts/run_tuning_benchmarks.py`` to orchestrate random/grid/Bayesian sweeps over scenario bundles, emit fresh telemetry reports, and produce the new per-scenario summaries in one shot.
- Recorded tuner metadata (`tuner_meta`) in telemetry runs (JSONL + SQLite), including algorithm labels, budgets, and configuration context, enabling downstream orchestration and comparison scripts to reason about search performance.
- `scripts/run_tuning_benchmarks.py` now generates `tuner_comparison.{csv,md}` and `tuner_leaderboard.{csv,md}` assets summarising best objective deltas, runtime averages, and win rates across algorithms.
- Introduced benchmark plans (`baseline-smoke`, `synthetic-smoke`, `full-spectrum`) with aligned tuner budgets; `scripts/run_tuning_benchmarks.py --plan` and CI smoke sweeps now reuse the documented matrix.
- Added `scripts/summarize_tuner_meta.py` utility to inspect `tuner_meta` payloads (per algorithm run counts, sample budgets/configs) and linked it from the telemetry how-to.
- Benchmark pipeline now emits per-bundle comparison/leaderboard tables and `tuner_difficulty*.{md,csv}` difficulty indices (including MIP gaps and second-best deltas), all published via GitHub Pages.
- `scripts/run_tuning_benchmarks.py` gained tier-aware budgets (`short`/`medium`/`long`) plus plan overrides; the runner forwards `--tier-label` to CLI tuners so telemetry pivots can separate budget tiers.
- Updated `docs/howto/telemetry_tuning.rst` and `notes/metaheuristic_hyperparam_tuning.md` with the tier matrix, hardware guidelines (≥64 cores, 8 GB RSS cap), and instructions for sequencing multiple tiers in one sweep.
- Integrated Iterated Local Search and Tabu Search into `scripts/run_tuning_benchmarks.py`; tier presets now drive their restart/iteration budgets, telemetry contexts record bundle/tier metadata, and `tests/test_run_tuning_benchmarks.py` exercises the new flags.
- Hardened comparison generation when runs lack bundle metadata (heuristic sweeps now default to `standalone` rather than raising).
- Docs/notes refreshed to outline the ILS/Tabu tier budgets and CLI overrides (`--ils-*`, `--tabu-*`) for smoke vs. deep sweeps.
- `scripts/analyze_tuner_reports.py` now accepts `--telemetry-log` and emits per-run/summary convergence reports (iterations to ≤1 % gap) by parsing step logs; the how-to adds usage guidance and tests cover the new outputs.
- Published a heuristic parameter catalogue in `docs/howto/telemetry_tuning.rst`, aligning the planning table with user-facing documentation so tuning surfaces are discoverable.

## 2025-11-11 — Telemetry KPI persistence
- Added a SQLite-backed telemetry mirror (`telemetry/runs.sqlite`) via `fhops.telemetry.sqlite_store.persist_run`, keeping run metadata, metrics, and KPI totals normalised alongside the JSONL history.
- Simulated annealing, ILS, and Tabu solvers now compute KPI bundles for every run, inject the totals into telemetry records, and persist them to both JSONL and SQLite stores.
- CLI tuners (`fhops tune-random`, `fhops tune-grid`, `fhops tune-bayes`) append `tuner_summary` records with per-scenario best objectives; regression tests assert the summaries and SQLite tables exist with KPI content.
- CLI tuning commands mirror their `tuner_summary` payloads into the SQLite store so benchmarking/reporting jobs can query sweep outcomes without parsing JSONL.
- Added `fhops telemetry report` to aggregate tuner performance into CSV/Markdown summaries sourced from the SQLite metrics and summary tables; coverage lives in `tests/test_cli_telemetry_report.py`.
- CI runs a lightweight minitoy sweep that generates `fhops telemetry report` artifacts (`telemetry-report` bundle) for baseline monitoring.
- Added `scripts/analyze_tuner_reports.py` plus tests, enabling deltas across multiple reports (baseline vs. experiment) to highlight objective improvements.
- Extended `scripts/analyze_tuner_reports.py` with historical reporting (`--history-dir`, CSV/Markdown/Altair outputs) so dated telemetry snapshots can be trended over time.
- CI now captures med42 alongside minitoy, publishes history summaries (`history_summary.{csv,md,html}`), and docs include a sample telemetry history figure plus a dedicated analysis notebook.
- Refreshed `notes/metaheuristic_hyperparam_tuning.md` and the roadmap to mark the telemetry persistence milestone and document the new storage layout.

## 2025-11-11 — Analytics notebook automation
- Added the analytics notebook runner to CI (`.github/workflows/ci.yml`) so the curated suite executes in light mode on every push/PR, exercising Altair plots and playback helpers.
- Captured fresh execution metadata in `docs/examples/analytics/data/notebook_metadata.json` and documented the `FHOPS_ANALYTICS_LIGHT` toggle in planning notes for reproducible smoke runs.
- Updated the analytics notebooks roadmap/planning entries to mark the runner + metadata milestones complete and highlighted follow-up documentation tasks.

## 2025-11-11 — Analytics notebooks theme closure
- Linked the notebook suite from the README and docs landing pages, describing how to regenerate runs locally with the light-mode flag.
- Documented full-mode runtimes in `notes/analytics_notebooks_plan.md`, concluded caching is unnecessary for now, and marked the Phase 3 analytics notebooks milestone complete in the roadmap.

## 2025-11-11 — Simulated annealing telemetry groundwork
- Added `RunTelemetryLogger`, a reusable JSONL context manager capturing run + step telemetry and exporting metadata for downstream tuning workflows.
- Instrumented `solve_sa` to emit telemetry (run id, configuration, metrics, step snapshots) when `telemetry_log` is provided; CLI multi-start now propagates context into these records.
- Extended telemetry logging to `solve_ils` and `solve_tabu`, including CLI wiring and regression tests, so all heuristics share the JSONL store with consistent run/step metadata.
- Added playback CLI telemetry: `fhops eval playback` now records run/step summaries via `RunTelemetryLogger`, emits artifacts/metrics, and exposes steps under `telemetry/steps/`; regression coverage ensures the JSONL line and step log are produced.
- Added `fhops telemetry prune` for trimming `runs.jsonl` and matching step logs to keep telemetry lightweight.
- Upgraded `fhops tune-random` to execute simulated annealing sweeps, sample operator weights, and record telemetry entries for each run.
- Introduced `fhops.telemetry.load_jsonl` to load telemetry JSONL records into dataframes for downstream analysis.
- Enriched heuristic telemetry (SA/ILS/Tabu) with scenario descriptors (counts of blocks/machines/landings/etc.) and recorded a telemetry schema version so future ML tuners can consume the data without schema retrofits.
- Added `fhops tune-grid` to exhaustively evaluate operator presets and batch-size combinations, logging results and telemetry for benchmarking against other tuning strategies.
- Added `fhops tune-bayes` (Optuna TPE) to perform Bayesian/SMBO searches over SA hyperparameters and log per-trial telemetry.
- Updated roadmap and tuning plan notes to reflect the schema draft and SA logging milestone; introduced regression tests ensuring telemetry logs are written with matching run identifiers.
- Added a placeholder `fhops tune-random` CLI command that surfaces recent telemetry records while the full random-search tuner is under construction.

## 2025-11-11 — Playback telemetry integration
- Extended `fhops eval playback` with a `--telemetry-log` option that records export metrics, sampling parameters, and artifact paths via the shared playback exporter helpers.
- Ensured playback exports reuse the canonical aggregation helpers in both deterministic and stochastic modes so telemetry reflects the exact CLI outputs.
- Added regression coverage (`tests/test_cli_playback_exports.py::test_eval_playback_telemetry_log`) asserting the JSONL payload captures scenario metadata and export metrics.
- Updated shift/day reporting planning notes to reflect the completed telemetry wiring.
- Added Hypothesis-based regressions (`tests/test_playback_aggregates.py::test_shift_totals_match_day_totals`, `test_blackout_conflicts_aggregate`) verifying shift/day totals reconcile and blackout conflicts aggregate correctly across stochastic configurations.
- Generated deterministic Parquet fixtures for minitoy/med42 playback outputs and extended the CLI regression to diff CLI Parquet exports against the stored schema snapshots.
- Expanded ``docs/howto/evaluation.rst`` with a CLI → Parquet → pandas quickstart, telemetry pointers, and an aggregation helper reference for KPI contributors.
- Added KPI-alignment regression ensuring playback aggregation outputs reproduce legacy KPI totals for minitoy/med42 fixtures.
- Introduced ``KPIResult`` structured mappings so KPI totals and shift/day calendars share a canonical schema exported via both playback helpers and CLI telemetry, and added utilisation, makespan, and landing-level mobilisation metrics to the KPI bundle.
- Added regression snapshots for deterministic/stochastic KPI outputs plus property-based coverage ensuring utilisation ratios stay within bounds, makespan aligns with productive days, and downtime/weather signals remain stable, alongside estimated production-loss metrics for downtime and weather events, a CLI `--kpi-mode` flag to toggle basic vs. extended KPI summaries, KPI reporting templates (Markdown/CSV), a stochastic robustness walkthrough under `docs/examples/`, and the completion of the Phase 3 KPI expansion milestone in the roadmap.
- Implemented a random synthetic dataset generator (`generate_random_dataset`) with CSV/YAML bundle support, produced small/medium/large reference datasets under `examples/synthetic/`, added statistical sanity tests over the generator outputs, regression coverage to keep the pipeline stable, and documented the bundles/metadata workflow in `docs/howto/synthetic_datasets.rst` (including CLI usage examples and the new `examples/synthetic/metadata.yaml` registry). The generator now samples tier-aware terrain/prescription tags, unique crew assignments with capability pools, richer blackout patterns, and emits `crew_assignments.csv` plus per-tier metadata so benchmarking/automation can reason about the synthetic library.
- Added the `fhops synth generate` CLI command with tier presets, config merging, preview mode, and regression coverage (`tests/test_cli_synth.py`), enabling scripted creation of synthetic bundles with crew assignments and metadata out of the box.
- Extended the CLI with `fhops synth batch`, allowing multi-bundle generation from plan files; added regression coverage (`tests/test_cli_synth.py::test_synth_batch_generates_multiple`) and updated docs to reflect the workflow.
- Refreshed the benchmarking harness/tests to cover the synthetic small bundle, enforced KPI sanity bounds, documented synthetic usage in the benchmarking how-to, and added automatic metadata aggregation updates whenever canonical bundles are regenerated (see `src/fhops/cli/synthetic.py`).
- Introduced weighted terrain/prescription sampling, blackout bias windows (`BlackoutBias`), and harvest-system mix support in the synthetic generator with targeted unit tests (`tests/test_synthetic_dataset.py::test_weighted_terrain_profile_skews_distribution`, `test_blackout_biases_increase_activity`, `test_system_mix_applies_when_systems_provided`) and property-based KPI checks (`tests/test_benchmark_harness.py::test_synthetic_kpi_properties`). Recorded medium/large tier scaling benchmarks in `notes/synthetic_dataset_plan.md`.
- Added tier-aware stochastic sampling presets (`SAMPLING_PRESETS`) surfaced via `sampling_config_for`, embedded the recommended ensemble settings in bundle metadata/CLI output, and added regression coverage for sampling overrides (`tests/test_synthetic_dataset.py::test_sampling_config_for_tier_defaults`, `test_sampling_config_override_merges`).
- Logged stochastic scaling experiments (medium/large tiers with sampling presets) and wired CI smoke coverage via `tests/test_synthetic_validation.py`; production/variance metrics captured in `notes/synthetic_dataset_plan.md`.
- Authored additional analytics notebooks (landing congestion, system mix, KPI decomposition, telemetry diagnostics, ensemble resilience, operator sweep, benchmark summary) with executed outputs under `docs/examples/analytics/`, plus supporting data files for reproducible runs.

## 2025-11-10 — Phase 3 playback planning kickoff
- Expanded the Phase 3 roadmap checklist with detailed subtasks covering playback upgrades, KPI expansion, synthetic datasets, analytics notebooks, and hyperparameter tuning deliverables.
- Logged the deterministic playback audit (current assets vs. gaps) inside `notes/simulation_eval_plan.md` to anchor upcoming shift/day reporting work.
- Authored the shift/day reporting specification (schemas, CLI surfaces, contract deltas) within `notes/simulation_eval_plan.md` and marked the roadmap subtask complete.
- Documented the playback migration checklist detailing module scaffolding, CLI integration, cleanup, and regression coverage, and checked off the corresponding roadmap item.
- Drafted the stochastic sampling API plan (sampling abstractions, CLI surface, testing strategy) and marked the RNG design subtask complete.
- Scaffolded the new playback package (`core.py`, `adapters.py`, `events.py`) with dataclasses, adapters, and Pydantic configs exported via `fhops.evaluation`.
- Implemented idle-hour and sequencing-violation accounting in the playback adapters/summaries to surface richer shift/day analytics ahead of CLI wiring.
- Added `tests/test_playback.py` with regression-problem coverage for block completion metadata, sequencing guards, and idle-hour aggregation.
- Introduced the `fhops eval playback` CLI command (table output + CSV export scaffolding) to run deterministic playback outside notebooks.
- Documented playback workflows in `docs/reference/cli.rst` and the new `docs/howto/evaluation.rst`.
- Added a CLI smoke test (`tests/test_cli_playback.py`) ensuring playback exports remain stable.
- Implemented stochastic playback scaffolding (`run_stochastic_playback`, downtime/weather events) with regression fixtures and unit coverage in `tests/test_stochastic_playback.py`.
- Added stochastic toggles to `fhops eval playback` (`--samples`, `--downtime-*`, `--weather-*`) and documented the workflow in the CLI reference/how-to.
- Extended CLI to expose landing shock parameters (`--landing-*`) with regression coverage.
- Added shift/day summary schema enhancements (sample IDs, utilisation ratios) plus Parquet/Markdown export options on `fhops eval playback`.
- Introduced playback aggregation helpers (`shift_dataframe`, `day_dataframe`, `machine_utilisation_summary`, etc.) with regression tests backing the new schema.
- Refactored playback exports into shared helpers (`playback/exporters.py`) and added CLI regression coverage (`tests/test_cli_playback_exports.py`).
- Extended stochastic playback tests with property-style checks covering deterministic equivalence and production bounds.
- Added landing shock sampling to the stochastic runner and regression coverage guarding production reductions.
- Checked off the playback inventory subtask in the roadmap to reflect the newly documented findings.

## 2025-11-09 — CLI profile integration hardening
- Refactored solver profile merging to return a structured `ResolvedSolverConfig`, simplifying how CLI commands consume operator presets, weights, batching, and extras.
- Updated `fhops solve-heur`, `solve-ils`, and `solve-tabu` to rely on the resolved config, improved multi-start seed handling, and ensured profile extras override CLI defaults safely.
- Tightened the benchmark suite (`fhops bench suite`) by reusing the resolved configs across SA/ILS/Tabu, normalising telemetry/summary metrics, and making scenario comparisons mypy-safe.
- Hardened ILS schedule reconstruction to tolerate mixed pandas dtypes and added regression coverage in `tests/test_cli_profiles.py` for the new resolver.
- Ran `ruff format`, `ruff check`, `mypy src`, and targeted pytest suites to keep lint/type/test gates green.
- Replaced `datetime.utcnow()` usage in CLI telemetry with timezone-aware `datetime.now(UTC)` to silence pytest warnings and emit explicit UTC offsets.
- Added a geopandas-free GeoJSON loader fallback so geospatial utilities and tests run in lean environments without the optional dependency.
- Normalised trailing whitespace in roadmap/planning notes and switched benchmark plotting utilities to import `Iterable` from `collections.abc` to keep pre-commit hooks clean.

## 2025-11-08 — Iterated Local Search rollout
- Implemented the `fhops.optimization.heuristics.solve_ils` Iterated Local Search solver with perturbation telemetry, hybrid MIP restarts, and operator stats parity with SA.
- Added a dedicated `fhops solve-ils` CLI command mirroring SA batching flags, plus `fhops bench suite --include-ils` options for harness comparisons.
- Expanded Sphinx docs: new how-to (`docs/howto/ils.rst`), CLI reference updates, telemetry schema notes, and parallel workflow cross-links covering ILS usage.
- Introduced unit coverage for ILS (basic run, operator filtering, hybrid MIP hook) to keep heuristics regressions green.
- Updated the roadmap/notes plan to reflect ongoing ILS/Hybrid milestone work (see `notes/metaheuristic_roadmap.md`).
- Increased `fhops bench suite` default MIP time limit to 1800 s so large84 benchmarks reach optimality without manual overrides; docs/roadmap updated accordingly.
- Began Phase 2 benchmark reporting enhancements: added a detailed plan (comparison metrics, visual artefacts, docs/test coverage) tracked in `notes/metaheuristic_roadmap.md` ahead of implementation.
- Enhanced benchmarking summaries with heuristic comparison columns (`solver_category`, best heuristic solver/objective, gap and runtime ratios) and added regression coverage/documentation so the new fields remain stable.
- Added a ``scripts/render_benchmark_plots.py`` helper plus Sphinx guidance/figures (`docs/_static/benchmarks/*.png`, `docs/howto/benchmarks.rst`) to visualise objective gaps and runtime ratios across heuristics.
- Drafted the new heuristics configuration how-to (`docs/howto/heuristic_presets.rst`) and wired it into the Sphinx navigation with cross-references to related guides.
- Expanded the benchmarking how-to with comparison table guidance and multi-solver CLI examples so readers can interpret the new metrics/plots.
- Refreshed the CLI reference (`docs/reference/cli.rst`) with a heuristic configuration quick-reference pointing to presets, advanced operators, and comparison plotting scripts.
- Added documentation maintenance notes covering benchmark figure regeneration (`docs/howto/benchmarks.rst`) and the hyperparameter tuning plan (`notes/metaheuristic_hyperparam_tuning.md`).
- Published the harvest system registry reference (`docs/reference/harvest_systems.rst`) and linked it from the data contract how-to.
- Added `docs/howto/system_sequencing.rst` covering scenario setup, solver workflows, and KPI interpretation for harvest system sequencing.
- Introduced CLI solver profiles (`--profile`, `--list-profiles`) with documentation updates in the heuristics and sequencing guides.
- Marked the harvest system sequencing milestone as complete in the Phase 2 roadmap.
- Planned documentation work for heuristic presets/benchmark interpretation (see `notes/metaheuristic_roadmap.md` Plan – Documentation Updates) ahead of drafting the new how-to content.

## 2025-11-07 — Planning Framework Bootstrap
- Established structured roadmap (`FHOPS_ROADMAP.md`) with phase tracking and detailed next steps.
- Authored coding agent runbook (`CODING_AGENT.md`) aligning workflow commands with Nemora practices.
- Seeded notes directory, backlog tracker, and Sphinx/RTD scaffolding to mirror the Nemora planning stack.
- Added `.readthedocs.yaml`, `docs/requirements.txt`, and a GitHub Actions workflow executing the full agent command suite.
- Refined `.readthedocs.yaml` using the Nemora template while still installing project extras for doc builds.
- Introduced `.pre-commit-config.yaml` to enforce lint/type standards via hooks.
- Bootstrapped modular package skeletons and migrated scenario contracts/loaders into `fhops.scenario`, leaving shims (`fhops.core.types`, `fhops.data.loaders`) with deprecation warnings.
- Updated CLI/solver modules to consume the new scenario contract/IO packages, refreshed ruff+mypy pytest configs (stubs, excludes), and brought `ruff format`, `ruff check`, `mypy`, `pytest`, and `pre-commit run --all-files` back to green.
- Ported the Pyomo builder, HiGHS driver, heuristics, and KPI helpers into the new `optimization/` and `evaluation/` packages with deprecated shims for `fhops.model/solve/eval`.
- Added shift timeline and mobilisation schemas to the scenario contract (`TimelineConfig`, `MobilisationConfig`) with planning notes/docs updated.
- Seeded synthetic scenario generator scaffolding (`SyntheticScenarioSpec`, `generate_basic`) and mobilisation unit tests; added scheduling/mobilisation models and updated Sphinx API docs.
- Implemented mobilisation setup-cost penalties across MIP/SA, added GeoJSON distance tooling (`fhops geo distances`) with example block geometries, and introduced default harvest system registry/notes from Jaffray (2025).
- Added distance-threshold mobilisation costs (transition binaries, SA evaluation alignment), shifted scenario contract to track harvest-system IDs, and expanded synthetic generator/tests for system-aware scenarios.
- Scenario contract now provides default harvest system registry linkage for blocks, with validation to ensure IDs align with the seeded BC systems.
- Added machine-role aware sequencing guardrails: MIP filters assignments by system job roles, SA heuristic honors the same, synthetic generator assigns roles, and new unit tests cover registry constraints and geo distance helpers.
- Synthetic generator now supports blackout timelines and exports machine roles; accompanying tests verify blackout handling.
- Added preliminary sequencing constraints (cumulative precedence) and heuristic enforcement, plus system role tests validating constraint activation.
- Planning updates: roadmap + MIP plan now track schedule-locking functionality for contractual/external commitments.
- Mobilisation workflow enhancements: auto-load distance matrices, report mobilisation spend in KPIs/CLI, and add tests for mobilisation KPI outputs.
- Began refactoring harvest-system sequencing into a dedicated constraint module, with builder invoking the shared helper ahead of future precedence logic.
- Refined harvest-system sequencing to enforce prior-day completion, aligned the SA heuristic evaluator with the stricter precedence logic, added regression coverage for both solvers, and updated the sequencing plan notes to reflect the milestone.
- Expanded sequencing coverage with cable and helicopter job chains, hardened the MIP constraint to enforce every prerequisite role individually, synced the SA evaluator and KPI metrics with the stricter checks, surfaced violation counts/breakdowns in CLI output, and added regression tests for sequencing KPIs.
- Introduced a mobilisation/blackout/sequence regression fixture, exercised it via new SA + MIP integration tests, and updated the Phase 1 roadmap and MIP plan checklists to reflect the added coverage.
- Added fixture baseline metrics (`tests/fixtures/regression/baseline.yaml`), updated regression tests to assert against them, and documented the scenario in the Sphinx quickstart for Phase 1 workflows.
- Expanded the quickstart, overview, and CLI reference to highlight baseline workflows and regression usage, and checked off the corresponding Phase 1 roadmap task.
- Hardened scenario contract validators (non-negative fields, horizon bounds, foreign-key checks, mobilisation distance integrity) with new unit coverage (`tests/test_contract_validations.py`).
- Extended schema validators to reject mobilisation configs referencing unknown machines, closing the linked-ID audit for CSV inputs.
- Added optional `GeoMetadata` and `CrewAssignment` helpers with validation, enabling typed extras for geospatial references and crew mapping.
- Authored `docs/howto/data_contract.rst` detailing CSV requirements, optional extras, and validator coverage; cross-linked from overview/quickstart.
- Documented GeoJSON ingestion expectations (CRS guidance, required IDs) and the `fhops geo distances` workflow for generating mobilisation matrices.
- Added parametrised validation tests (`tests/test_contract_edge_cases.py`) to exercise edge-case scenarios across the data contract, introduced `tests/data/*` fixtures with loader coverage, published authoring guidance in the data-contract how-to, refreshed the README quickstart, introduced explicit `schema_version` support in scenarios, and extended the loader/docs to ingest timeline configs plus crew/geo metadata.
- Integrated timeline blackouts across the MIP builder and SA heuristic, expanded fixtures/tests to cover crew/timeline ingestion, and updated the data-contract docs with timeline examples.
- Validated GeoJSON ingestion via the scenario loader (block/landing paths, CRS/id checks), refreshed fixtures/docs, wired CLI usage into the data contract guidance, and added regression fixtures/tests covering the new metadata.
- Added schedule-locking support (scenario contract → MIP builder + SA heuristic), objective weight toggles, and regression coverage for the new constraints/workflow documentation.
- Enabled `.github/workflows/ci.yml` to run the full coding-agent command suite (ruff format/check, mypy, pytest, pre-commit, Sphinx) on pushes and PRs.
- Recorded the decision to keep invalid references fatal in `notes/data_contract_enhancements.md` to ensure strict validation remains the default.
- Cleaned up the SA heuristic lock handling, stabilised the schedule-locking regression test by initialising all mobilisation transition binaries, and refreshed the mobilisation regression baseline to reflect the objective-weighted behaviour.
- Cleared Read the Docs configuration gaps by keeping `.readthedocs.yaml` in sync, eliminated Sphinx duplicate-target warnings (`:noindex:` on package aggregators, corrected RST underlines), switched intersphinx inventories to `None`, and checked in the geo/locked fixtures plus `_static/.gitkeep` used by the validation tests.
- Mocked heavy runtime dependencies (`geopandas`, `highspy`) while ensuring core libs (`pydantic`, `pyomo`, `pandas`, `pyyaml`, etc.) install via `docs/requirements.txt` so RTD autodoc renders module content with real model definitions.
- Extended objective handling with transition and landing-slack weights; the Pyomo builder now introduces transition binaries even without mobilisation configs, landing slack variables when penalised, and the SA heuristic mirrors the weighted scoring. Added targeted unit tests covering transition and slack penalties.
- Bumped package metadata to `v0.0.1` and finalised the Phase 1 release notes, preparing the PR for the GitHub release workflow trigger.
- Relaxed the `require-changelog-update` hook to support `pre-commit run --all-files` (CI no longer fails when the latest commit already updates `CHANGE_LOG.md`).
- Added the Phase 2 benchmarking harness (`fhops bench suite`) with structured outputs, regression fixture for minitoy SA, and accompanying documentation/tests.
- Calibrated mobilisation setups for the bundled minitoy/med42/large84 scenarios, wired loader support for inline mobilisation configs, refreshed benchmark baselines to assert mobilisation spend (including per-machine breakdowns), documented CLI usage, added geo-distance regression coverage, and documented projection/tooling guidance for GeoJSON ingestion.
- Documented the current simulated annealing defaults (temperature schedule, restarts, neighbourhoods), added SA-specific metrics (acceptance rate, objective gap vs MIP) to the benchmarking harness, refreshed regression fixtures/tests, and cross-linked CLI/docs with tuning guidance.
- Refactored the SA neighbour generation with explicit swap/move operators, paving the way for a pluggable operator registry in subsequent metaheuristic work.
- Finalised the Phase 2 shift-based scheduling plan: roadmap and modular reorg notes now outline the shift-aware data contract, solver refactors, KPI/CLI updates, and migration guidance.
- Added shift calendar support to the scenario contract/loader (including regression coverage) so scenarios can specify per-shift machine availability ahead of full shift-aware scheduling.
- Reindexed the Pyomo MIP builder, mobilisation/landing constraints, and sequencing helper to operate on shift tuples, updated the HiGHS driver/benchmark harness to emit shift-aware assignments, refreshed regression/locking/mobilisation/system-role tests, and captured the milestone in `notes/mip_model_plan.md`.
- Shift-enabled the simulated annealing schedule representation, evaluation, and neighbour plumbing to operate on `(day, shift_id)` indices, updated SA output DataFrames accordingly, and refreshed the metaheuristic roadmap plus regression/unit tests with shift-aware helpers.
- Extended the SA greedy initialiser and blackout checks to honour shift-level availability (calendar entries or timeline-defined shifts), ensuring locked assignments and blackout penalties match the shift-aware MIP behaviour; roadmap updated to reflect the milestone.
- Synced CLI/docs/tests with shift-aware SA outputs (assignment CSVs now include `shift_id`, docs note the new column, and locking tests assert shift-level fixes) to close the output alignment task.
- Hardened SA neighbourhood operators to respect shift-level availability and blackouts, sanitising invalid swaps/moves and updating the minitoy benchmark fixture to the new acceptance metrics.
- Shift-aware SA objective evaluation now honours shift availability, mobilisation transitions, landing slack, and blackout penalties per `(day, shift)` slot, bringing heuristic scoring in line with the MIP objective.
- Regression suite now asserts that SA assignment exports carry `shift_id` values and updates the metaheuristic roadmap to reflect the completed test alignment work.
- Marked the Phase 2 shift-based scheduling architecture milestone complete after upgrading data contract, MIP/SA solvers, benchmarks, and KPI reporting to operate on `(day, shift_id)` indices.
- Planned the next wave of metaheuristic expansion (operator registry, advanced neighbourhoods, Tabu/ILS prototypes, benchmarking/reporting upgrades) and captured the milestones in `notes/metaheuristic_roadmap.md`.
- Broke down the operator registry scaffold task into actionable sub-steps (registry design, SA integration, CLI surface, telemetry, testing, docs) recorded in `notes/metaheuristic_roadmap.md` for execution tracking.
- Added detailed sub-subtasks for the registry data model (context dataclass, protocol, registry API, default operators, unit tests) to guide implementation.
- Implemented the initial registry scaffold by introducing `OperatorContext` and sanitizer typing primitives (`fhops.optimization.heuristics.registry`) and exporting them via the heuristics package.
- Added an `Operator` protocol defining the standardized name/weight/apply interface for heuristic operators to support the upcoming registry.
- Implemented `OperatorRegistry` providing `register`, `get`, `enabled`, `configure`, and `from_defaults` helpers to manage heuristic operators and their weights.
- Ported the existing swap/move neighbourhood logic into standalone operators registered via `OperatorRegistry.from_defaults()`, updated SA neighbour generation to run through the registry, and refreshed the minitoy benchmark baseline for the new behaviour.
- Added unit tests covering the operator registry defaults, weight configuration, and sanitizer integration.
- Captured a detailed sub-plan for operator registry integration within SA (registry wiring, shared sanitizer reuse, operator weighting, regression verification) in `notes/metaheuristic_roadmap.md`.
- Rewired SA neighbours to iterate through the registry with weighted operator selection while reusing the shared sanitizer, keeping regression/benchmark outputs stable.
- Reran the benchmark/regression suites post-registry integration, updated the minitoy baseline, and checked off the verification subtask in `notes/metaheuristic_roadmap.md`.
- Exposed operator configuration flags in the CLI (`solve-heur`, `fhops bench suite`), ensured benchmark summaries record `operators_config`, added parsing tests, and documented the new options.
- Added operator presets (balanced, move-only, swap-heavy, swap-only, diversify) with CLI support and helper utilities for parsing/validation.
- Instrumented per-operator telemetry in SA (`operators_stats`), surfaced stats in CLI/bench summaries, documented the new tuning signals, and described the telemetry schema in `docs/reference/telemetry.rst`.
- Added JSONL telemetry logging utilities with CLI `--telemetry-log` support, enabling persistent storage of SA run metadata for future hyperparameter tuning workflows.
- Captured detailed design specs for advanced neighbourhood operators (block insertion, cross-machine exchange, mobilisation shake) in `notes/metaheuristic_roadmap.md`, including context dependencies, telemetry fields, and pseudo-code to guide the upcoming implementation phase.
- Implemented advanced neighbourhood operators (`block_insertion`, `cross_exchange`, `mobilisation_shake`) in the registry with shared helper utilities, wired them into the default registry (weight=0.0) and CLI presets, and marked the implementation subtask complete in `notes/metaheuristic_roadmap.md`.
- Added shift-aware SA operator presets (`explore`, `mobilisation`, `stabilise`) with documented weight profiles, updated CLI helpers/tests to expose the new options, and captured usage guidance in `docs/reference/cli.rst`.
- Extended the benchmarking harness with `--compare-preset` sweeps, labelled summary/telemetry outputs (`preset_label`), and per-preset assignment exports to evaluate the new operators side-by-side; roadmap notes updated accordingly.
- Added unit coverage for the advanced operators (`tests/heuristics/test_operators.py`) ensuring block insertion honours windows/availability, cross exchange respects machine capabilities, and mobilisation shake observes lock and spacing rules.
- Added regression assertions so the advanced presets (explore/mobilisation/stabilise) maintain the mobilisation baseline objective when enabled.
- Separated simulated annealing RNG seeding from the global `random` module by constructing a local generator per solve, keeping regression/benchmark runs deterministic without side effects.
- Fixed the `large84` example mobilisation config to reference the actual machine IDs (H1–H16), reran SA-only benchmark sweeps to confirm diversification presets still outperform baseline, and recorded a follow-up to raise the full-suite timeout before release.
- Added an opt-in multi-start controller (`fhops.optimization.heuristics.multistart.run_multi_start`) with coverage to run multiple SA instances in parallel and select the best objective while collecting per-run telemetry.
- Added a deterministic seed/preset exploration helper (`build_exploration_plan`) plus unit tests for the multi-start module.
- Multi-start runs now support JSONL telemetry logging (per-run records with run IDs and a summary entry) via the optional `telemetry_log` parameter.
- Added opt-in batched neighbour generation in SA (`batch_size`, `max_workers`) with threadpool evaluation and parity tests.
- Extended `fhops solve-heur` CLI with `--parallel-multistart`, `--parallel-workers`, and `--batch-neighbours` flags, including guardrails, telemetry fields, and updated CLI docs for parallel workflows.
- Documented parallel workflows in Sphinx (multistart/batched how-to, CLI references, telemetry notes) and benchmarked the parallel heuristics across minitoy/med42/large84 to guide defaults.
- Added an experimental Tabu Search solver (`solve_tabu`), shared CLI options/telemetry, and initial unit coverage.
- Integrated Tabu Search into the benchmarking harness (`fhops bench suite --include-tabu`) and recorded comparative results showing SA remains the default recommendation.
- Introduced a synthetic scenario dataset generator (`generate_random_dataset`) with CSV/YAML bundle writer helpers, scenario plan updates, and regression coverage (`tests/test_synthetic_dataset.py`) to support Phase 3 benchmarking workflows.
- Added optional Gurobi backend support (extra `fhops[gurobi]`, CLI `--driver gurobi`, fallback-friendly solver plumbing), documented Linux licence setup, and extended the MIP ingestion helper to accept driver overrides for heavier baselines.
