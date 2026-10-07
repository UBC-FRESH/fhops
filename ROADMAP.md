# FHOPS Roadmap

This roadmap orchestrates FHOPS’ evolution into a production-ready planning platform. It
mirrors the multi-level planning system pioneered in Nemora: top-level phases here, with
module-specific execution plans living in `notes/`. Update the checklist status and the
"Detailed Next Steps" section as deliverables land. When in doubt, consult the linked notes
before proposing new work.

## Phase 0 — Repository Foundations ✅ (complete)
- Initial project scaffold (`pyproject.toml`, CLI entry point, examples).
- Baseline tests covering core data contract and solver smoke cases.
- Basic README explaining architecture and usage.

## Phase 1 — Core Platform Hardening ✅ (complete)
- [x] Harden data contract validations and scenario loaders (see `notes/data_contract_enhancements.md` and `docs/howto/data_contract.rst`).
- [x] Expand Pyomo model coverage for production constraints and objective variants (see `notes/mip_model_plan.md`).
- [x] Stand up modular scaffolding (`notes/modular_reorg_plan.md`) and shift-level scheduling groundwork (`scheduling/timeline` + timeline-integrated solvers).
- [x] Establish deterministic regression fixtures for MIP and heuristic solvers.
- [x] Document baseline workflows in Sphinx (overview + quickstart).
- [x] Stand up CI enforcing the agent workflow command suite on every push and PR (see `notes/ci_cd_expansion.md`).
- [x] Define geospatial ingestion strategy for block geometries (GeoJSON baseline, distance matrix fallback) to support mobilisation costs (`notes/mobilisation_plan.md`, `notes/data_contract_enhancements.md`, `docs/howto/data_contract.rst`).

## Phase 2 — Solver & Heuristic Expansion
- [x] Scenario scaling benchmarks & tuning harness (phase kickoff task).
- [ ] Shift-based scheduling architecture (data contract → solvers → KPIs) (`notes/modular_reorg_plan.md`, `notes/mip_model_plan.md`, `notes/simulation_eval_plan.md`).
- [x] Metaheuristic roadmap execution (Simulated Annealing refinements, Tabu/ILS activation).
- [x] Mobilisation penalty calibration & distance QA across benchmark scenarios (`notes/mobilisation_plan.md`).
- [x] Harvest system sequencing parity and machine-to-system mapping (`notes/system_sequencing_plan.md`).
- [x] CLI ergonomics for solver configuration profiles.

## Phase 3 — Evaluation & Analytics
- [x] Robust schedule playback with stochastic extensions (downtime/weather sampling) and shift/day reporting.
  - [x] Playback engine audit
    - [x] Inventory deterministic playback path (`fhops/eval`, `scheduling/timeline`) and capture gaps in `notes/simulation_eval_plan.md`.
    - [x] Spec shift/day reporting interfaces and required data contract updates.
    - [x] Produce migration checklist for refactoring playback modules and regression fixtures.
  - [x] Stochastic sampling extensions
    - [x] Design RNG seeding + scenario ensemble API and land it as a draft in `notes/simulation_eval_plan.md`.
    - [x] Implement downtime/weather sampling operators with unit and property-based tests.
    - [x] Integrate sampling toggles into CLI/automation commands (document defaults in `docs/howto/evaluation.rst`).
  - [x] Shift/day reporting deliverables
    - [x] Define aggregation schemas for shift/day calendars and extend KPI dataclasses.
    - [x] Add exporters (CSV/Parquet + Markdown summary) wired into playback CLI.
    - [x] Validate outputs across benchmark scenarios and stash fixtures for CI smoke runs.
- [x] KPI expansion (cost, makespan, utilisation, mobilisation spend) with reporting templates.
  - [x] Metric specification & alignment
    - [x] Reconcile definitions across `notes/mip_model_plan.md`, `notes/mobilisation_plan.md`, and simulation notes.
    - [x] Document final KPI formulas and assumptions in `docs/howto/evaluation.rst`.
    - [x] Map required raw signals from playback outputs and ensure data contract coverage.
  - [x] Implementation & validation
    - [x] Extend KPI calculators to emit cost, makespan, utilisation, mobilisation spend variants.
    - [x] Add regression fixtures and property-based checks confirming KPI ranges per scenario tier.
    - [x] Wire KPIs into CLI reporting with configurable profiles and smoke tests.
  - [x] Reporting templates
    - [x] Draft tabular templates (CSV/Markdown) plus optional visuals for docs/notebooks.
    - [x] Provide Sphinx snippets and CLI help examples showcasing new KPI bundles.
    - [x] Capture follow-up backlog items for advanced dashboards (e.g., Plotly) if deferred (defer to backlog).
- [x] Synthetic dataset generator & benchmarking suite (`notes/synthetic_dataset_plan.md`).
  - [x] Design & planning
    - [x] Finalise dataset taxonomy and parameter ranges in `notes/synthetic_dataset_plan.md`.
    - [x] Align generator requirements with Phase 2 benchmarking harness expectations.
    - [x] Identify storage strategy and naming for generated scenarios (`data/synthetic/`).
  - [x] Generator implementation
    - [x] Build core sampling utilities (terrain, system mix, downtime patterns) with tests.
    - [x] Expose CLI entry (`fhops synth`) and configuration schema for batch generation.
    - [x] Add validation suite ensuring generated datasets meet contract + KPI sanity bounds.
  - [x] Benchmark integration
    - [x] Hook synthetic scenarios into benchmark harness and CI smoke targets.
    - [x] Provide metadata manifests describing each scenario for docs/examples.
    - [x] Outline scaling experiments and capture results in changelog/notes.
- [x] Reference analytics notebooks integrated into docs/examples.
  - [x] Notebook scaffolding
    - [x] Select representative deterministic + stochastic scenarios (baseline + synthetic).
    - [x] Define notebook storyboards (playback walkthrough, KPI deep-dive, what-if analysis).
    - [x] Create reusable plotting helpers (matplotlib/Altair) shared across notebooks.
  - [x] Notebook authoring
    - [x] Draft notebooks under `docs/examples/analytics/` with executed outputs.
    - [x] Ensure notebooks call CLI/modules via lightweight wrappers for reproducibility.
    - [x] Capture metadata (runtime, dependencies) and add smoke execution script.
  - [x] Documentation & automation
    - [x] Integrate notebooks into Sphinx (nbsphinx or nbconvert pipeline) with cross-links.
    - [x] Add CI check to execute notebooks (or cached outputs) on critical scenarios.
    - [x] Update README and docs landing pages to advertise analytics assets.
- [ ] Hyperparameter tuning framework (conventional + agentic) leveraging persistent telemetry (`notes/metaheuristic_hyperparam_tuning.md`).
  - [x] Telemetry & persistence groundwork
    - [x] Define telemetry schema (solver configuration, KPIs, runtime stats) and storage backend (drafted in `notes/metaheuristic_hyperparam_tuning.md`).
    - [x] Implement logging hooks in solvers and playback runs, persisting to local store.
      - [x] Simulated Annealing JSONL run logger emitting run/step telemetry (`RunTelemetryLogger`, `solve_sa`).
      - [x] ILS + Tabu telemetry integration (run/step logging, CLI wiring).
      - [x] Playback CLI telemetry (run metadata + step logging for day summaries).
      - [x] Enrich telemetry with scenario descriptors and schema versioning for ML tuners.
    - [x] Document data retention/rotation strategy in tuning notes.
  - [ ] Conventional tuning toolkit
    - [x] Implement grid/random/Bayesian search drivers leveraging telemetry store.
    - [x] Provide CLI surfaces for launching tuning sweeps with scenario bundles.
      - [x] Random tuner CLI (`fhops tune-random`) executing SA sweeps and recording telemetry.
      - [x] Bayesian/SMBO tuner CLI (`fhops tune-bayes`) built on Optuna.
    - [x] Automate CI sweeps (tiny7 + med42) that publish `fhops telemetry report` artifacts and history summaries for baseline scenarios (CSV/MD/HTML + published chart).
    - [ ] After merging Phase 3 PR, verify GitHub Pages deployment on `main` (ensure `telemetry/history_summary.html` loads).
      - [x] Grid tuner CLI (`fhops tune-grid`) evaluating preset/batch-size combinations.
    - [x] Add automated comparison reports summarising best configurations per scenario class.
    - [ ] Benchmark tuner strategies (grid vs. random vs. Bayesian/SMBO vs. neural/agentic) and log meta-telemetry for automated model selection.
    - [x] Introduce dual convergence thresholds (soft ≤5%, hard ≤1%) in telemetry analytics so automated stopping criteria have rich signals.
    - [x] Parallelise the tuning harness (≈16 worker processes × 4 threads) with per-worker telemetry merge so sweeps scale linearly with hardware.
    - [x] Add optional Gurobi backend (`fhops[gurobi]`, `--driver gurobi`) for MIP solves that outgrow HiGHS.
    - [x] Run long-horizon convergence sweeps (SA/ILS/Tabu, ≥10 000 iterations) on baseline + synthetic bundles to measure iteration/runtime scaling and tune stopping heuristics.
      - `tmp/convergence-long/long_run_summary.csv` captures wall-clock rates and gap progress; only SA/ILS on `synthetic-medium` reached ≤5 % gap within 10 000 iterations, highlighting the need for deeper budgets or enhanced operators elsewhere.
      - Next: rerun SA/ILS/Tabu with ≥MIP wall-clock budgets (≥10 min) and log Z* vs. iteration/time curves for regression against scenario size/difficulty.
    - [ ] Reporting polish
      - [x] Tighten `_compute_history_deltas` so percentage columns remain valid and Markdown renders cleanly.
      - [x] Confirm README + docs/how-to explicitly reference the GitHub Pages URL and the exported delta artefacts.
      - [x] Expand `DESIRED_METRICS` (e.g., downtime) once telemetry logging exposes the required fields.
  - [ ] Agentic tuning integration *(deferred — see Backlog & Ideas; focus remains on conventional toolkit completion).*

## Phase 4 — Release & Community Readiness
- [x] Complete Sphinx documentation set (API, CLI, how-tos, examples) published to Read the Docs (`notes/sphinx-documentation.md`, `docs/howto/release_playbook.rst`, `docs/howto/telemetry_ops.rst`, `docs/howto/thesis_eval.rst`, API narrative guides).
  - 2025-11-24: Closed the Sphinx/docstring audit (feature/api-docstring-enhancements) — all CLI, evaluation, heuristics, and productivity modules now ship NumPy-style docstrings and Sphinx builds are warning-free.
- [x] Finalise contribution guide, code of conduct alignment, and PR templates (see `docs/howto/release_playbook.rst`, `CONTRIBUTING.md`, `AGENTS.md`).
- [x] Versioned release notes and public roadmap updates (`docs/releases/v1.0.0.md`, `docs/releases/v1.0.0-alpha2.md`, `docs/releases/v1.0.0-alpha1.md`, `docs/releases/v0.1.0.md`, `ROADMAP.md` current).
- [ ] Outreach plan (blog, seminars, partner briefings).

## Phase 5 — Formal Model Documentation Synchronization
- [ ] Publish the operational MILP formulation as a canonical source module shared across manuscript and docs.
- [ ] Keep SoftwareX manuscript, Sphinx how-to docs, and thesis chapter text synchronized from one formulation source.
- [ ] Maintain an equation-to-code traceability table (`operational.py` and `data.py` mapping).
- [ ] Add a regression check ensuring formulation assets regenerate cleanly (`export_docs_assets.py` + docs build).

## Phase 8 — 1.0.1 Maintenance (rolling-horizon carry-forward + playback fixes)
Parent #90; branch `feature/phase8-v101-maintenance` (from tag `v1.0.0`); plan `notes/v101_maintenance_plan.md`.
Phases 6–7 (tactical–operational 1.1.0a line) live on `main`; this phase is forward-ported there.
- [x] #91 Optional `Scenario.initial_state` honoured by MILP, heuristics, and playback.
- [x] #92 Rolling-horizon state carry-forward plus lock/blackout/shift fixes.
- [x] #93 Stochastic playback event fixes (landing-shock days, downtime duration, `correlated_days`).
- [x] #94 Document `Block.work_required` units (m³).
- [x] #95 SoftwareX playback figure legibility and regenerated playback assets.
- [ ] #96 Release FHOPS 1.0.1 and forward-port to `main`.
- [x] #99 Working operational-MILP warm start with HiGHS (`appsi_highs` MIP start, documented per-solver fallback).
- [x] #100 Validate YAML `locked_assignments` (and other optional sections) against the scenario in `load_scenario`.
- [x] #108 Correct KPIs for empty and partial plans (an empty assignment table no longer reports full delivery).
- [x] #109 Align operational-MILP and playback/heuristic sequencing semantics (MILP plans replay with zero violations).
- [x] #110 Enforce timeline blackouts in the operational MILP (zero availability, same slots as the heuristics).
- [x] #116 Pre-release audit fixes: multi-shift heuristic landing regression, head-start waiver timing, `shift_id` required on multi-shift playback, index-agnostic events, shift-hours fallback, record-level loss KPIs, landing-shock presets, deprecated sampling fields, `eval-playback` help.
- [x] #118 Pre-release audit: lock window/role and `role_remaining` validation, verified dependency floors, CLI tests in CI, compatibility docs, unrelated `config/` removed from the repo and sdist.
- [x] #115 Operational MILP robustness and correctness (audit): no-raise driver with solver-error reporting, idle-feasible locks, per-upstream inventories for joins, dynamic loader threshold, `min(R, W)`, fleet-wide blackouts on partial shift calendars.
- [x] #117 Rolling-horizon robustness (audit): no-solution windows recorded and left idle (`--fail-on-empty-window` to stop), empty-window flags, up-front lock-window check, partial shift calendars, independent replay tests.
- [x] #119 SoftwareX benchmark asset consistency (audit): stale med42 SA assignment CSVs regenerated (rows reproduced exactly), manuscript tables rebuilt (med42 tuning sense fixed), playback `metrics.json` reports delivered volume, `audit_asset_consistency.py` added.
- [x] #124 Legacy `solve_mip` / `fhops solve-mip` / `fhops benchmark` no longer raise for infeasible, no-incumbent or failed solves (operational-driver result contract, documented exit codes); rolling MILP hook forwards driver `solver_error`/`warnings`; in-repo manuscript version and dependency statements corrected.
- [x] #127 Legacy MIP builder retired: `fhops solve-mip` / `solve_mip` are deprecated aliases of the operational MILP (same result contract and exit codes), `fhops benchmark` uses the operational MILP, and the ILS hybrid step warm-starts the operational MILP from the ILS schedule (closes #104).

## Detailed Next Steps
0. **Phase 8 — 1.0.1 maintenance (`notes/v101_maintenance_plan.md`)**
   - 2026-10-06: #91 (`issue-91-initial-state-contract`) adds optional `Scenario.initial_state` and `ScheduleLock.shift_id`, honoured by the operational MILP (first-slot inventory/head-start, role-remaining cap, boundary move, lock constraints), heuristics, and playback, with v1.0.0 regression parity tests. Next: #92 rolling-horizon carry-forward builds on this contract.
   - 2026-10-06: #99 (`issue-99-highs-warm-start`) fixes the `--incumbent` `TypeError` with HiGHS: seeded HiGHS solves go through Pyomo's `appsi_highs` MIP start, the result/CLI/telemetry report whether HiGHS accepted the start, unsupported solvers warn (`MilpWarmStartWarning`), and limit-stopped solves keep their incumbent.
   - 2026-10-06: #95 (`issue-95-playback-figure`) redraws the SoftwareX playback figure for legibility (manuscript text width, 9 pt text, legend above the panels) and regenerates only the playback assets with the #93 event fixes; deterministic benchmark/tuning/scaling assets unchanged and SA re-solves reproduce the committed tiny7/small21 summaries.
   - 2026-10-06: #92 (`issue-92-rolling-carry-forward`) replays the stitched locked plan on the base scenario after every iteration (`carry_forward_state`) and slices the next window with remaining volume + `initial_state`; user locks are merged into every window, blackouts rebased, locks keep `shift_id`, hooks record runtime and resolve `solver="auto"` to HiGHS. Follow-ups noted in the plan: empty-plan KPI artefact, MILP blackouts, end-of-window valuation, MILP/playback same-day inventory mismatch.
   - 2026-10-06: #108 (`issue-108-empty-plan-kpis`) fixes the empty-plan KPI artefact: playback always carries a sequencing tracker, `compute_kpis` reports the delivered volume (0 for an empty plan, remaining = Σ `work_required`), and `compute_rolling_kpis` scores an empty baseline as zero delivery (an empty rolling plan still raises).
   - 2026-10-06: #109/#110 (`issue-109-milp-playback-alignment`) align the operational MILP, heuristics, and playback sequencing rules (slot-level release, volume head starts, per-role output caps, unsequenced blocks, shift order, planned production in MILP rolling locks) so MILP plans replay without violations, and enforce timeline blackouts in the MILP. Reference-ladder heuristic results unchanged.
   - 2026-10-06: #116 (`issue-116-heuristics-playback-audit`) fixes the multi-shift SA/ILS/Tabu regression from #109 (the repair stacked every role of a block on its landing per shift; it now respects landing capacity on multi-shift days — Jaffray ka_6/pg_6/ka_18 SA reach full delivery with 0 penalties), times the head-start waiver like the MILP, requires `shift_id` on multi-shift playback, and corrects the playback/KPI/stochastic findings of the audit. Reference ladder and SoftwareX playback assets byte-identical.
   - 2026-10-06: #118 (`issue-118-contract-packaging-audit`) closes pre-release audit findings: locks outside block windows or on incompatible roles and `role_remaining > work_required` are rejected; dependency floors raised to verified versions (`pyomo>=6.9.2`, `highspy>=1.8.1`, `typer>=0.12.4`, `PyYAML>=6.0.1`); operational-MILP/playback CLI tests run in CI; compatibility with 1.0.0 documented; the unrelated `config/` app state is removed and excluded from builds (secret rotation pending with the maintainer).
   - 2026-10-06: #115 (`issue-115-milp-robustness`, pre-release audit) hardens the operational MILP: the driver never raises for infeasible/no-incumbent solves and reports HiGHS errors as errors; locked machines may sit idle (no lock-induced infeasibility); joins use per-upstream staged inventories; the loader threshold follows the remaining block volume; `role_remaining` is capped at `work_required`; blackouts block every grid slot. Linear loader-free models are byte-identical; tiny7 optimum unchanged (4388.082752).
   - 2026-10-06: #117 (`issue-117-rolling-robustness`) hardens rolling horizon after the pre-release audit: MILP windows without a solution no longer crash (recorded, lock span idle, optional `fail_on_empty_window`; CLI always writes partial outputs), empty windows are flagged and counted, locks outside block windows are rejected up front, windows outside a partial shift calendar get no shifts, and the replay tests are strengthened (independent linear-chain state machine, slot-order aware).
   - 2026-10-06: #119 (`issue-119-softwarex-asset-consistency`) audits every SoftwareX benchmark/table/playback/scaling/tuning asset: all committed benchmark rows reproduce exactly on 1.0.1; the stale med42 SA default/diversify assignment CSVs and the stale manuscript tables are regenerated (published values unchanged), playback `metrics.json` reports delivered volume. Open: manuscript scaling runtimes come from another run; heuristic objectives omit some cached mobilisation (pre-existing).
   - 2026-10-06: #124 (`issue-124-legacy-mip-hook-warnings`) aligns the legacy `solve_mip` with the operational driver (no raise; `has_solution`/`outcome`/`solver_error`/`warnings`; `solve-mip` exits 1 only on solver error/unavailable), forwards driver errors/warnings through the rolling MILP hook, and fixes the in-repo manuscript's FHOPS version and dependency lists. Finding: the legacy MIP's loader-buffer constraint makes every bundled example infeasible (also in 1.0.0); documented, formulation fix deferred.
   - 2026-10-06: #127 (`issue-127-legacy-mip-retirement`) retires the infeasible legacy MIP: `solve-mip`/`solve_mip` warn and delegate to the operational MILP (driver mapping documented), `benchmark` and `bench suite --driver auto` solve the operational MILP (HiGHS fallback restored), the ILS hybrid step passes the ILS schedule as a HiGHS MIP start (#104), and every `solve-mip` doc example now uses `solve-mip-operational`. Reference ladder byte-identical.
1. **Release Candidate Prep (`notes/release_candidate_prep.md`, `AGENTS.md`, `notes/cli_docs_plan.md`)**
   - Lock feature set, refresh install/docs, and draft release notes + Hatch-based packaging checklist ahead of the public milestone.
   - 2026-06-14: v1.0.0 GA issue tree opened; first child branch (`issue-15-v100-green-ci`) is restoring the green CI/local verification gate before release metadata changes.
   - 2026-06-14: second child branch (`issue-16-v100-version-docs`) bumps package metadata/docs to the final `1.0.0` release line before artifact and publication work.
   - 2026-06-14: third child branch (`issue-17-softwarex-v100-metadata`) aligns in-repo SoftwareX manuscript metadata/prose with the final `v1.0.0` release links and install path.
   - 2026-06-14: fourth child branch (`issue-18-v100-artifact-smoke`) validates final `1.0.0` artifacts, fixes clean wheel runtime dependencies/package data, moves the full-text reference-document vault to a private `reference-documents` submodule for copyright-risk control, and records the public-bibliography vs. private-source-document content policy.
   - 2026-06-14: fifth child branch (`issue-19-release-surface-audit`) audits public release surfaces, annotates the confusing `v0.0.1-alpha3` prerelease, fixes the manual release-build path, and hardens the full analytics notebook artifact workflow before the final publication issue.
   - 2026-06-14: sixth child branch (`issue-27-docs-readiness`) sweeps user-facing docs before publication, fixing broken README rendering, stale CLI examples, source-checkout/PyPI wording, and release-note status.
2. **Metaheuristic Roadmap (`notes/metaheuristic_roadmap.md`)**
   - Prioritise SA refinements, operator registry work, and benchmarking comparisons with the new harness (including shift-aware neighbourhoods).
3. **Shift-Based Scheduling Refactor (`notes/modular_reorg_plan.md`, `notes/mip_model_plan.md`, `notes/simulation_eval_plan.md`)**
   - Add shift-indexed data contract fields/validators, migrate loaders + fixtures, update MIP/heuristic decision variables to `(day, shift)` granularity, and extend playback/KPI exports plus CLI/docs to surface shift-level results.
4. **Harvest System Sequencing Plan (`notes/system_sequencing_plan.md`)**
   - Close parity gaps between MIP/heuristic sequencing and add stress tests for machine-to-system mapping.
5. **CLI & Documentation Plan (`notes/cli_docs_plan.md`)**
   - Introduce solver configuration profiles/presets and document shift-based workflows in the CLI reference.
6. **Simulation & Evaluation Plan (`notes/simulation_eval_plan.md`)**
   - Prepare deterministic/stochastic playback for shift timelines and extended KPI reporting ahead of Phase 3.
7. **Telemetry Dashboards & Reporting Polish (`docs/howto/telemetry_tuning.rst`, `docs/reference/dashboards.rst`)**
   - Add interpretation/playbook sections for each published dashboard, embed consolidated landing views (iframes or raw HTML) into Sphinx, and backfill testing/automation notes so CI coverage extends to the full notebook suite.
   - Automate a weekly “full” analytics notebook run (no `--light`) via a scheduled GitHub Actions workflow that uploads refreshed artefacts to the telemetry bundle and alerts if any notebook fails.
   - Capture operational expectations (rotation owners, notification channel, artifact retention) in `notes/metaheuristic_hyperparam_tuning.md` once the workflow lands.
8. **Productivity Modeling & Helper Rollout (`notes/dataset_inspection_plan.md`, `docs/reference/harvest_systems.rst`)**
   - [x] Ship CTL forwarder helper module (`fhops.productivity.forwarder_bc`) covering Ghaffariyan small/large, Kellogg mixed/saw/pulp, and FPInnovations ADV6N10 sorting models, with CLI/test coverage and planning notes.
   - [x] Ship CTL harvester helpers (ADV6N10 regression + CLI, ADV5N30 removal/brushing modifiers, TN292 tree-size/density regression) and document applicability in the CLI/docs.
   - [x] Record TN285 / ADV5N9 / ADV2N21 scenario guidance (ghost trails, removal levels, trail reuse) in the planning docs so scenario authors know when productivity stays flat vs. when to adjust costs.
   - [x] Integrate the new helpers into dataset inspection CLI defaults and synthetic generator presets; refresh fixtures/tests that assume legacy productivity values (landing processor/loader coverage now fully wired, docs/tests refreshed).
   - [x] Keep `ROADMAP.md` and `notes/dataset_inspection_plan.md` in sync as additional FPInnovations regressions are ported.
   - **Next focus:** with the TN258 monthly support split, Hi-Skid costing, and ADV4N7/ADV15N3 penalties now wired directly into the cost helper, pivot to the November 2025 FPInnovations drop scan (TN122+/ADV salvage set) so the outstanding “new PDF” backlog can close without waiting for fresh references.
9. **SoftwareX Manuscript Phase 2 (`notes/softwarex_manuscript_plan.md`)**
   - Resume drafting + reproducibility prep on the new `feature/softwarex-phase3` branch now that the MIP formulation work merged back into `main`.
   - Close the remaining Phase 2 checkboxes (Section 1–3 polish, reproducibility callouts) and queue Phase 3 validation reruns (`generate_assets.sh`, `run_synthetic_sweep.py`, `make pdf`) for the next manuscript sync.
   - Sync the manuscript plan + change log after each writing/automation block so roadmap status always reflects the in-flight work.
10. **Dataset Inspection CLI (`notes/dataset_inspection_plan.md`)**
    - Capture UX/requirements for the post-v0.1.0-a1 dataset-inspection tooling so shipped bundles (tiny7/small21/med42) and synthetic presets no longer ship with unrealistic parameters.
    - Design the first CLI pass that loads any dataset (by path or canonical name) and emits parameter summaries for GIGO prevention; Python API can follow later.
    - Resolve open questions around dataset scope, stats vs. raw outputs, and non-interactive flags before implementation starts.
11. **Rolling-Horizon Replanning (`notes/rolling_horizon_plan.md`)**
    - Build a rolling-horizon orchestration layer (scenario slicing, lock-in state, iterative solve loop) so FHOPS can emit multi-month “locked” plans from tractable subproblems.
    - Expose both CLI (`fhops plan rolling`) and Python API helpers, starting with planning machinery (SA baseline) and deferring evaluation/reporting to a later phase.
    - Log per-iteration telemetry so MASc-led studies can quantify suboptimality vs. full-horizon baselines once the planning engine stabilizes.
12. **Operational MILP Formulation Sync (`docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md`)**
    - Keep the canonical operational MILP formulation synchronized across SoftwareX manuscript, Sphinx docs (`docs/howto/optimization_formulation.rst`), and thesis chapter integration assets.
    - Preserve code-to-equation traceability against `src/fhops/model/milp/operational.py` and `src/fhops/model/milp/data.py`.
    - Add lightweight regeneration/build checks to catch drift between Markdown source and generated `.tex`/`.rst` includes.

## Backlog & Ideas
- [ ] Agentic tuner R&D (prompt loop, guardrails, benchmarking) — revisit once the conventional tuning suite and reporting pipeline are stable.
- [ ] Integration with Nemora sampling outputs for downstream operations analytics.
- [ ] Scenario authoring UI and schema validators for web clients.
- [ ] Cloud execution harness for large-scale heuristics.
- [ ] DSS integration hooks (ArcGIS, QGIS) for geo-enabled workflows.
- [ ] Jaffray MASc thesis alignment checkpoints (`notes/thesis_alignment.md` TBD).
- [ ] VSCode keeps firing web apps on various random-sounding ports while running `injest_mip_baselines.py` and other benchmarking scripts? What is up with that? It is annoyingly resulting in VSCode interface popping up "Your application is running on port XXXX" messages (becaue of the built-in port-forwarding proxy).
- [ ] Schedule “full” analytics notebook runs (no light flag) on a less frequent cadence (nightly or weekly: leaning towards weekly) to guard against stochastic regression while keeping CI duration manageable.
  - [ ] Extend CI with a `cron` job that invokes `scripts/run_analytics_notebooks.py --timeout 900` (no `--light`) and publishes the resulting reports to the telemetry Pages bundle, keeping a 4-week artifact history for comparison.
- [ ] `pre-commit` autoupdate (especially `pre-commit-hooks`) plus workflow wiring so stage deprecation warnings are resolved before upstream removal.
- [ ] Dataset inspection + data-quality polish (see `notes/dataset_inspection_plan.md`)
  - [ ] Enforce/document 24 h/day machine availability in docs + sample datasets, and flag deviations via the inspector CLI.
