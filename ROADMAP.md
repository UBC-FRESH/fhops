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
  - [x] Progressive onboarding series under `examples/` complete: `00_fhops_orientation.ipynb`, `01_fhops_operations_simulation.ipynb`, `02_fhops_solve_compare.ipynb`, `03_fhops_playback_kpis.ipynb`, and `04_fhops_stochastic_what_if.ipynb` cover API/CLI execution, operations simulation, and notebook-local AAM-style helpers.
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
- [x] #57 Audit canonical formulation sources and approve the shared source/ADR layout for operational and tactical–operational MILPs (merged via PR #61).
- [x] #58 Publish the operational MILP formulation as a canonical source module shared across manuscript and docs, with current `operational.py`/`data.py` traceability (merged via PR #62).
- [x] #59 Publish the tactical–operational MILP formulation as a canonical source module shared across Sphinx/manuscript assets, with `tactical_operational.py` traceability (merged via PR #63).
- [x] #60 Add regression/drift checks ensuring formulation assets regenerate cleanly (`export_docs_assets.py` + docs build) (merged via PR #64).

## Phase 6 — Tactical–Operational Expansion (TOPM-Inspired)
- [x] #37 Approve the architecture, scope boundaries, workflow contract, and TOPM/OperMAX provenance baseline in `notes/tactical_operational_expansion_plan.md` (merged via PR #45).
- [x] #38 Add a period-hierarchical, unit-explicit tactical–operational data contract while preserving schema `1.0.0` operational workflows (merged via PR #46).
- [x] #39 Implement the core multi-year harvest/system/period model with semi-continuous minimum cut sizes and discounted economics (merged via PR #47).
- [x] #40 Integrate products, transport, facilities, inventory, consumption, and outside purchases (merged via PR #48).
- [x] #41 Add optional roads, silviculture transitions, and fleet investment/economic-life modules (merged via PR #49).
- [x] #42 Add scenario overlays/diffs, auditable accounting reports, and TOPM-shaped synthetic acceptance fixtures (merged via PR #50).
- [x] #43 Couple aggregate tactical decisions to the existing shift-indexed operational and rolling-horizon engines (merged via PR #51).
- [x] #44 Benchmark scale/decomposition options only after the integrated core is validated and profiled (merged via PR #52; full 5-year benchmark and practitioner validation remain follow-up scope).

## Phase 7 — Tactical Validation Scale-Up and Release Preparation
- [x] #75 Integrate Phase 7 into `main` (merged via PR #84).
- [x] #76 Run and document the full 5-year / 500+ block TOPM-shaped tactical benchmark with profiling evidence (merged via PR #80).
- [x] #77 Build a redistributable practitioner-scale tactical validation case and verify decisions/balances/reports (merged via PR #81).
- [x] #78 Add an executable guided tactical planner notebook covering contract → solve → report → operational handoff (merged via PR #82).
- [x] #79 Prepare the FHOPS version bump and release notes after validation evidence lands (merged via PR #83).

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
- [x] #125 Solver consistency: operational-MILP landing capacity per shift slot and hard at `landing_surplus = 0` (as the heuristics; formulation E11 corrected), multi-shift day locks expanded to every available shift in rolling replay/exports, idle locked slots not flagged by playback, `fhops evaluate` input errors without traceback.
- [x] #136 SR-109 green-tree cost multiplier 1.10 → 1.09; unused `click` dependency dropped; Typer floor corrected to `typer>=0.15.4`.
- [x] #129 Block `harvest_system_id` validated against `Scenario.harvest_systems` + the default registry (the 1.0.0 check never ran; regression fixture now registers its `ground_sequence` system); every `fhops …` command in the README/docs run against the shipped examples and the broken ones fixed.
- [x] #103 Dataset CLI under Typer ≥ 0.26: `--fncy12-variant` / harvest-system-default usage errors fixed (option-source check now version-agnostic), `--kpi-mode` usage errors instead of tracebacks, and the dataset CLI test suites run in CI.
- [x] #139 Operational MILP objective/semantics (audit 2): staying on a block is no transition, moves across idle slots and from the carried-in block are charged as in the heuristics/KPIs (exact per-machine position network, much smaller model), no-op loader batching integers removed, fork/join/head-start semantics documented, solver exceptions (Gurobi licences) reported with `auto` → HiGHS fallback, `fhops build-mip` deprecated onto the operational MILP, deprecation warnings visible from scripts.
- [x] #141 Rolling-horizon MILP deferral (audit 1, round 2): lexicographic earliness tie-break in rolling MILP windows (base objective unchanged; `--no-mip-earliness`, `solve-mip-operational --earliness`), idle lock spans flagged empty, `--fail-on-empty-window` stops on empty windows (+ `--fail-on-no-solution`), `plan rolling` exit codes (1 when no window has a solution, 2 for bad horizons/`--max-iterations`/unavailable solver), MILP hook no longer swallows FHOPS exceptions.
- [x] #131 Exact heuristic objective and SoftwareX asset regeneration.
  - [x] Code: the SA/ILS/Tabu search score equals a fresh `evaluate_schedule` of the same plan (complete mobilisation cache, idempotent multi-shift repair, idle locked slots kept, Tabu seed scored with the full repair) and the reported objective is a fresh evaluation of the exported schedule.
  - [x] Regenerate all SoftwareX benchmark/tuning/playback/costing/dataset/scaling assets on the final 1.0.1 candidate (one sequential full run on an idle host, 3 h 48 min; tables and figures rebuilt; `benchmark_runs.log` entry; asset audit passes with the objective check promoted to pass/fail; manuscript old → new values in `notes/v101_maintenance_plan.md` §8.21).
- [x] #140 Heuristic landing guard on every day (capacity-0 landings admit no machine; downstream roles with staged input hold landing places, so hard capacities no longer starve the pipeline), hard-violation penalty that dominates one assignment, planned-production scoring of MILP plans (`evaluate_assignments`, ILS hybrid adoption), and documented/reported `AUTO_OBJECTIVE_WEIGHT_OVERRIDES` with like-for-like MIP vs SA comparisons in `benchmark`/`bench suite`; med42/synthetic SoftwareX assets to be regenerated.
- [x] #144 SoftwareX asset provenance hygiene: verifiable assets hash (recipe v2 over the committed files, `asset_hash.py verify`), repo-relative recorded paths (writers fixed, current assets normalised), Table 5 shows every tuner budget and what Δ compares, in-repo manuscript draft marked superseded with metadata facts corrected, tracked `.continue/` removed from git and sdists.
- [x] #151 Heuristic performance regression from #140 fixed without changing any search result: operators decide rejected moves from the edited slots (no schedule copy or full sanitizer pass per try), faster repair (incremental landing counts, best-rate-first block choice); scaling tiers and med42 back at or below 0463fd5 runtimes.
- [x] #152 Labelled canonical operational formulation: OBJ/OBJ2/E1–E13 (E8a–c)/INIT/D1 labels, Block → Pyomo mapping table, docs page anchor `operational-milp-formulation` for citation, drift test (no code change).
- [x] #147 Final SoftwareX asset regeneration on the final 1.0.1 code (50e6f9b, incl. the #151 performance fix): one sequential full pipeline run on an idle host (2 h 57 min; `assets_hash` 5e069c58…, recipe v2, `asset_hash.py verify` passes), tables/figures rebuilt, asset audit 0 failures, plans/objectives identical to the superseded a0b2799 run (#150); manuscript values manuscript → committed → new in `notes/v101_maintenance_plan.md` §8.28.
- [x] #158 Third-audit heuristic fixes: locked slots produce what their input allows and may idle (no lock-induced sequencing violations; `ScheduleLock.production` cap), blocks without fleet roles admit no machine (`fhops validate` warns), repair capped by block remaining; synthetic generator derives fleet roles from the system mix; synthetic tiers regenerated (synthetic-small 39.79 m³ delivered; scaling 13.2/39.3/65.1 s), reference ladder and Jaffray unchanged (plan §8.32).

## Phase 11 — Log Hauling and Mill Delivery Optimization (Ghotb-Inspired) ✅ (complete)
Parent #170; branch `feature/p11-log-hauling` (merged as `52462d2`); plan
`notes/log_hauling_expansion_plan.md`; issue tree `notes/log_hauling_issue_tree.md`.
Adds the operational log-hauling layer missing between harvest and mill demand: Phase I monthly
daily-flow MIP with contractor workload balance, Phase II continuous-time truck/loader scheduling,
and a thesis-calibrated SA solver.
- [x] #172 P11.1 Provenance, hauling contract, and formulation audit.
- [x] #173 P11.2 Phase I monthly flow MILP and goal programming.
- [x] #174 P11.3 Phase II daily routing and scheduling MILP.
- [x] #175 P11.4 SA solution approach, SPT decoder, and calibration.
- [x] #176 P11.5 FHOPS integration, CLI, reporting, and example case.
- [x] #177 P11.6 Validation, documentation, formulation sync, and close-out.
- [x] #187 P11.7 Marine/barge haul legs: explicit `TransportMode`, `BargeType`/`Barge`, `Port`,
  `WaterArc`, `PortLeg`, and `MarineRoute`; Phase I water/terminal flow tables; deterministic
  barge-cycle scheduling with port-load synchronization; Sunshine Coast → Howe Sound fixture and
  contract/flow/schedule/CLI tests.

## Phase 12 — FHOPS Web Application (WS4-Style) — complete
Parent #171; branch `feature/p12-web-ui` (active from 2026-10-25); plan
`notes/web_ui_expansion_plan.md`; issue tree `notes/web_ui_issue_tree.md`.
Adds an optional FastAPI + vanilla-ES-module web surface over the CLI's artefacts, following the
WS4 web UI design. The same application covers three lenses: shift-level operational planning
(machine/crew day-shift Gantt, assignments, playback, KPIs), Ghotb-derived log hauling (Phase I
flows/truckloads, Phase II/III truck/loader schedule, yard inventory, contractor workload, haul
KPIs), and TOPM-style tactical-operational planning (period harvest decisions, product flows,
facility demand/inventory, roads, silviculture, fleet). It adds map/layer tree, domain Gantt/tables,
reports, comparison, live SSE runs, domain skins, and an opt-in assistant.
- [x] #178 P12.1 Service skeleton, run manifest, artefact discovery, and CLI entry.
- [x] #179 P12.2 Read-only API, SPA shell, and skin loader.
- [x] #180 P12.3 Map, layer tree, and day/period control.
- [x] #181 P12.4 Schedule/Gantt, KPI, report, and comparison panels.
- [x] #182 P12.5 Live runs, SSE, and run control.
- [x] #183 P12.6 Editable objective/locks, assistant, packaging, security, docs, and close-out.

## Phase 13 — Multi-day Marine Barge Cycles — complete
Parent #197; branch `feature/phase13-multiday-marine`; design
`notes/multiday_marine_cycles.md`.
Extends the P11.7 marine path so a barge voyage can span more than one day
without adding dummy barges or relaxing capacity checks.
- [x] #196 P13.1 Design multi-day marine cycles and add the failing regression fixture.
- [x] #199 P13.2 Implement multi-day marine departure/arrival timing.
- [x] Close-out report: `notes/reports/p13-closeout.md`.

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
   - 2026-10-06: #125 (`issue-125-landing-locks-alignment`) makes SA and MILP judge landing feasibility identically: the operational MILP counts machines per landing and shift slot (was machine-shifts per day with a slack that was free at weight 0) and treats the capacity as hard at `landing_surplus = 0`; locks exceeding a hard capacity raise that slot's limit with a warning. tiny7 MILP optimum 4388.082752 → 279.796036 (capacity-1 landings now bind). Rolling replay/carry-forward/exports expand day-level locks to every available shift; playback no longer flags idle locked slots; `fhops evaluate` exits 1 with a message on invalid input. Reference ladder and SoftwareX playback assets byte-identical.
   - 2026-10-07: #129 (`issue-129-harvest-system-validation-docs`) validates block `harvest_system_id` at scenario level (model validator; the 1.0.0 field validator never ran because `harvest_systems` is declared after `blocks`); only the repository regression fixture was affected (custom `ground_sequence` system now registered in its YAML; all other repo/SoftwareX scenarios and the nine Jaffray scenarios load unchanged). Docs sweep: every `fhops …` command in README/docs run or (long-running/Gurobi) parsed and run with small budgets/HiGHS; broken options, ids and snippets fixed.
   - 2026-10-07: #131 (`issue-131-heuristic-objective-cache`, code part) makes the heuristic objective exact: candidates' mobilisation caches now cover every machine (unchanged machines were free before), the multi-shift landing guard no longer makes the repair non-idempotent, idle locked slots are kept, Tabu scores its seed with the full repair, and SA/ILS/Tabu report a fresh evaluation of the exported schedule. Heuristic results change on all scenarios with mobilisation (tiny7 plans unchanged, objective −10.748). Next: regenerate the SoftwareX assets once all Phase 8 code has merged.
   - 2026-10-07: #103 (`issue-103-dataset-cli-tests`) fixes the 53 gated dataset CLI test failures. All had one root cause: Typer 0.26 vendors Click, so `_parameter_supplied` (identity check against `click.core.ParameterSource.DEFAULT`) reported every option as user-supplied. Skyline calls were rejected and harvest-system defaults were never applied (a user-facing bug since Typer 0.26.0, before v1.0.0). The check now compares by name; `--kpi-mode` uses a `StrEnum`; the tests are unchanged and now run in CI (+145 tests, ≈ 4 s).
   - 2026-10-07: #131 (`issue-131-regenerate-assets`) regenerates every SoftwareX asset on the final 1.0.1 candidate with the canonical pipeline (benchmarks now sequential, tuning budgets fixed to the published ones, text normalised to the pre-commit rules) and makes FHOPS assets the source of record for the manuscript, scaling runtimes included. All manuscript tables/figures and several prose values change (old → new table in plan §8.21); the asset audit now fails when a reported objective differs from a fresh evaluation of its CSV.
   - 2026-10-07: #140 (`issue-140-landing-guard-scoring`, second pre-release audit) applies the heuristic landing guard on single-shift days too (every published med42 heuristic plan overloaded landings 49–61 times; med42 SA 20000 iterations −28662.40 → 24130.32, 0 overloads, 10 completed blocks), scales the hard-violation penalty so an infeasible plan cannot beat the MILP's hard optimum, scores MILP plans with their planned production in the ILS hybrid step, surfaces the Tiny7/Small21 automatic weight overrides (notice, meta/telemetry, scenario-weight objective in `benchmark`/`bench suite`), and (audit2-1 #2) lets downstream roles with staged input hold landing places so a hard capacity no longer starves the pipeline (feller → skidder → loader on a capacity-1 landing: SA 0 → 500 m³ = MILP). tiny7/small21 bench assets byte-identical; Jaffray ka_6/pg_6 SA objectives unchanged (full delivery). Next: regenerate the med42/synthetic SoftwareX assets.
   - 2026-10-07: #139 (`issue-139-milp-objective-semantics`) fixes the second audit's MILP findings: transitions only for `b' ≠ b`; a per-machine position network charges moves across idle slots and from `last_block_id` into the first worked slot exactly like the heuristics and KPIs (fuzz 400/400 exact; tiny7 optimum unchanged 279.796036, brute-force verified; non-binding-landing tiny7 4388.082752 → 4361.462752; med42 at 600 s finds a 216-assignment incumbent instead of none); loader batching integers removed; solver exceptions never escape, `solver="auto"` falls back to HiGHS; `build-mip` deprecated; deprecation warnings attributed to the caller; formulation regenerated.
   - 2026-10-07: #144 (`issue-144-asset-hygiene`, audits 3/4) makes the SoftwareX provenance verifiable without re-running anything: `benchmark_runs.log` hashes only the files git would commit (LC_ALL=C, log excluded; recipe in the manuscript README, `make verify-assets-hash`), an `audit_note` entry records the corrected 0463fd5 hash (committed files: 16a4def7…), the pipeline records repo-relative paths (32 committed files normalised, byte-identical otherwise), Table 5 gains a Budget column and a Δ/SA-budget note, the in-repo draft points to UBC-FRESH/fhops-manuscript, and `.continue/` no longer ships. Next: regenerate the SoftwareX assets on the final code.
   - 2026-10-07: #141 (`issue-141-rolling-deferral-cli`) stops rolling MILP windows from deferring work past their lock span: a lexicographic earliness stage (max production-weighted earliness subject to the base objective ≥ stage-1 value − 10⁻⁶ relative) runs in every window whose lock span is shorter than the window (defer.py: days 8–10 → 1–3; ka_6 112/14/7: 59 idle days and work until day 112 → all work by day 27, 0 idle). Idle lock spans now count as empty windows; `--fail-on-empty-window` stops on them, `--fail-on-no-solution` keeps the old meaning; `plan rolling` exits 1 when no window has a solution and 2 for usage errors; formulation documents the tie-break.
   - 2026-10-08: #151 (`issue-151-heuristic-perf`) fixes the heuristic slowdown found by the #147 regeneration (synthetic-small SA 3×, scaling tiers non-monotonic, med42 +41–82 %). Root cause: since #140 the repaired plan is a sanitizer fixed point, so block insertion / cross exchange / mobilisation shake retried ~276 moves per call, each with a full schedule copy and sanitizer pass; on med42 the #140 repair work (reservation scan, landing checks). Fix: `SanitizerPreview`, incremental landing counts, best-rate-first block choice, exact fast shuffle; identical plans to a0b2799 everywhere tested (plan §8.29).
   - 2026-10-08: #152 (`issue-152-labelled-formulation`) makes the labelled formulation canonical in FHOPS so the SoftwareX R2 manuscript can replace its 17-page appendix with a compact one citing the versioned source. Content reconciled with the manuscript's labelled copy in favour of the 1.0.1 text (plan §8.30); TeX/RST regenerated; new `tests/test_docs_formulation_assets.py`.
   - 2026-10-08: #147 (`issue-147-final-asset-regeneration-v2`) regenerates every SoftwareX asset on the final 1.0.1 code (50e6f9b) with the canonical pipeline on an idle host (the a0b2799 run, PR #150, was superseded by the #151 fix; plans and objectives are byte-identical, only runtimes move). tiny7/small21 unchanged apart from runtimes; med42 objectives become positive with 0 hard violations (ILS 24329.17 best), synthetic-small −53039.79 → −39.79, Table 5 med42 Tabu Δ −990.50; every runtime is lower than in the manuscript and the scaling runtimes stay monotonic (20.69 / 45.86 / 69.22 s). Several manuscript statements change (plan §8.28). Next: manuscript update and #96 release.
   - 2026-10-08: #158 (`issue-158-audit3-heuristics`, third audit) makes locked slots idle instead of violating when their input is missing (fuzz: heuristic-only hard violations 78/200 → 0; lockpull −2200 → −200 = MILP), gives blocks without fleet roles an empty allowed set (phantom production 400 m³ → 0) with a `fhops validate` warning, and makes synthetic tiers deliverable (fleet roles from the system mix); partial asset regeneration of the synthetic tiers (log entry 17:47:01Z, hash 5be2f878…); tiny7/small21/med42 and Jaffray byte-identical (plan §8.32).
1. **Release Candidate Prep (`notes/release_candidate_prep.md`, `AGENTS.md`, `notes/cli_docs_plan.md`)**
   - Lock feature set, refresh install/docs, and draft release notes + Hatch-based packaging checklist ahead of the public milestone.
   - 2026-06-14: v1.0.0 GA issue tree opened; first child branch (`issue-15-v100-green-ci`) is restoring the green CI/local verification gate before release metadata changes.
   - 2026-06-14: second child branch (`issue-16-v100-version-docs`) bumps package metadata/docs to the final `1.0.0` release line before artifact and publication work.
   - 2026-06-14: third child branch (`issue-17-softwarex-v100-metadata`) aligns in-repo SoftwareX manuscript metadata/prose with the final `v1.0.0` release links and install path.
   - 2026-06-14: fourth child branch (`issue-18-v100-artifact-smoke`) validates final `1.0.0` artifacts, fixes clean wheel runtime dependencies/package data, moves the full-text reference-document vault to a private `reference-documents` submodule for copyright-risk control, and records the public-bibliography vs. private-source-document content policy.
   - 2026-06-14: fifth child branch (`issue-19-release-surface-audit`) audits public release surfaces, annotates the confusing `v0.0.1-alpha3` prerelease, fixes the manual release-build path, and hardens the full analytics notebook artifact workflow before the final publication issue.
   - 2026-06-14: sixth child branch (`issue-27-docs-readiness`) sweeps user-facing docs before publication, fixing broken README rendering, stale CLI examples, source-checkout/PyPI wording, and release-note status.
   - 2026-06-15: issue #20 closes the v1.0.0 GA tree by publishing `fhops==1.0.0` to TestPyPI/PyPI, pushing the annotated `v1.0.0` tag, verifying the tag-triggered release-build workflow, and creating the public non-prerelease GitHub release.
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
12. **Formal Model Documentation Sync (#56; `notes/formal_model_sync_issue_tree.md`)**
    - Child issues #57–#60 are merged into `feature/phase5-formal-model-sync` via PRs #61–#64.
    - Canonical operational and tactical–operational MILP formulations are synchronized across Markdown sources, generated TeX/RST includes, Sphinx docs, and manuscript-facing assets.
    - `scripts/check_formulation_assets.py` now regenerates formulation assets into a temporary tree and fails on checked-in drift; traceability tests cover both MILP mapping tables.
    - Final gate complete: Phase 5 integration PR #65 merged into `main`, closing parent #56.
13. **Tactical–Operational Expansion (#36; `notes/tactical_operational_expansion_plan.md`, `notes/tactical_operational_issue_tree.md`)**
    - Parent issue #36 and child issues #37–#44 are linked via GitHub sub-issues; all child PRs #45–#52 are merged into `feature/phase6-tactical-operational-expansion`.
    - The phase branch now carries the two-level architecture, tactical contract/MILP, product-flow/inventory/infrastructure modules, scenario overlays/reporting, tactical→operational handoff, and initial scale telemetry.
    - Final gate complete: Phase 6 integration PR #53 merged into `main`, closing parent #36.
    - Follow-up scope is tracked separately: full 5-year/500+ block benchmark, practitioner case validation, guided planner notebooks, decomposition if measured scale requires it, and the pre-existing notebook full-pre-commit debt.
14. **Tactical Validation Scale-Up and Release Preparation (#75; `notes/tactical_validation_issue_tree.md`)**
    - Phase branch `feature/phase7-tactical-validation-release` carried child issues #76–#79 for full-scale benchmarking, practitioner validation, guided planner documentation, and the FHOPS 1.1.0a1 alpha version bump.
    - All child PRs #80–#83 merged into the phase branch; Phase 7 integration PR #84 merged into `main`, closing parent #75.
    - The version bump was gated on benchmark and practitioner evidence because Phase 6 materially expands FHOPS's potential use cases.
    - SoftwareX manuscript edits are out of scope here; the manuscript lives in the separate `fhops-manuscript` repository.

15. **SA Performance and Incremental Repair (#165, #166; `notes/sa_performance_plan.md`, `notes/p10_repair_refactor.md`, ADR 0003)**
    - P9 S4a lazy candidate evaluation (2.1x, identical objectives); S2 (dirty-only repair) dropped and S3 (nested hot path) reverted, both recorded.
    - P10 block-separable evaluator, bounded `cross_exchange` sampling (ADR 0003), lazy pre-repair, and the incremental repair, which is now the SA default and behaviour-identical (72/72 parity; pinned baselines regenerate with no diff).
    - Session throughput ~3.6x (geometric mean) on the example ladder; today's P10.5/P10.6 increment ~1.48x.
    - Close-out report `notes/reports/p10-closeout.md`; PR #167 queued into `main`.

16. **Log Hauling and Mill Delivery (#170; `notes/log_hauling_expansion_plan.md`, `notes/log_hauling_issue_tree.md`)**
    - Queued as P11. The phase adds the operational hauling layer between harvest and mill demand:
      Ghotb's Phase I monthly daily-flow MIP with contractor workload balance, Phase II
      continuous-time truck/loader scheduling, and the SA solver with an SPT decoder.
    - Child issues #172-#177 are linked as sub-issues; the phase branch merged as `52462d2` and the parent is closed.
    - The thesis case data is confidential, so acceptance uses structural fidelity, MIP-versus-SA
      parity on thesis-shaped synthetic instances, and the published qualitative findings. Exact
      company-dollar reproduction is explicitly not claimed.
    - #172-#177 are complete. The phase PR #185 merged as `52462d2`; the close-out report is `notes/reports/p11-closeout.md`.

17. **FHOPS Web Application (#171; `notes/web_ui_expansion_plan.md`, `notes/web_ui_issue_tree.md`)**
    - Queued as P12. The phase adds an optional FastAPI + vanilla-ES-module SPA over CLI artefacts,
      following the WS4 web UI design: map/layer tree, schedule, KPIs, reports, comparison, live SSE
      runs, skins, and an opt-in assistant.
    - Child issues #178-#183 are linked as sub-issues; all six are complete on `feature/p12-web-ui`.
    - P12.1 freezes the artefact contract (including a new `run.json`) before the API and UI work.
      P11 hauling outputs are optional; missing layers are named, not invented.
    - #178-#183 (service, API/shell, map/layers/time, domain panels/KPIs/reports/comparison, live runs/SSE/control, editing/assistant/packaging/security/close-out) are complete.

## Phase 14 — Consume FEMIC-compiled LidarBC Products — complete

Parent issue: #188. Branch: `feature/phase14-lidar-products`.

Goal: pin and validate FEMIC LidarBC bundles, map terrain/canopy products into
block/landing support, and preserve native-resolution provenance without
reimplementing discovery or materialization.

- [x] P14.1 Define the FHOPS consumer contract for FEMIC LidarBC products (#189)
  - [x] Pin bundle id/version and per-product checksums
  - [x] Validate manifest, licence, CRS, resolution, vertical datum, and source tiles
  - [x] Add polygon support summaries without reprojection
  - [x] Add optional scenario `lidar_products`/`lidar_support` pins and loader validation
  - [x] Validate shared slope/CHM parity with WS4
- [x] P14.2 Register and consume FEMIC-packaged products for scenario AOIs (#190)
  - [x] Validate bundles and write stable bundle/manifest/product pins
  - [x] Record scenario AOI bbox and CRS compatibility
  - [x] Add `fhops scenario lidar validate|register` and operator docs
- [x] P14.3 Map FEMIC terrain and canopy products into FHOPS scenarios (#191)
  - [x] Summarize native-resolution products over block/landing/road support
  - [x] Record product, aggregation, resolution, valid pixels, support area, and provenance
  - [x] Add `fhops scenario lidar map` and mapping tests
- [x] P14.4 Integrate terrain/canopy with harvest-system operability and cost (#192)
  - [x] Add advisory ground/cable/helicopter classification and fallbacks
  - [x] Compare current systems and recommend class-compatible systems
  - [x] Add advisory move-in/landing/road cost context and validation note
- [x] P14.5 Build and validate a precision-forestry scenario fixture (#193)
  - [x] Commit the public TFL 6 fixture with block/landing/road terrain/canopy support
  - [x] Record bundle/product provenance, licence, and synthetic-table labels
  - [x] Add regeneration script, fixture tests, and cross-repo WS4 parity
  - [x] Record operability and schedule smoke results with limits
- [x] P14.6 Validate, document, and close out P14 (#194)
  - [x] Run the real-bundle validate/map/operability/smoke-solve path
  - [x] Record WS4 parity, timings, storage, and OGL-BC evidence
  - [x] Fix repeated-section YAML duplication with regression tests
  - [x] Write `notes/reports/p14-closeout.md` and `notes/reports/p14-validation.json`

Acceptance:

- FHOPS can validate and pin a FEMIC bundle.
- Polygon support summaries preserve the product CRS and native resolution.
- Shared-AOI slope/CHM values match WS4 within the documented tolerance.
- The public fixture validates, runs, and records licence/provenance and limits.
- No discovery or materialization is reimplemented in FHOPS.

## Phase 15 — Consume FEMIC hydrology response bundles — complete

Parent issue: #218. Branch: `feature/phase15-hydrology-consumer`.

Goal: pin and validate a FEMIC hydrology bundle, map FHOPS blocks/landings/roads
through an explicit reviewed crosswalk, consume a schedule-bound road/culvert
exposure table, and screen one operational schedule. This is a read-only
consumer and screening phase, not a flood model or real watershed pilot.

Authoritative note: `notes/phase15_hydrology_consumer.md`.
Closeout: pull request #232 squash-merged as `3b404414`; the phase report is
`notes/reports/p15-closeout.md`.

- [x] P15.1 Define the FHOPS hydrology consumer contract (#219)
  - [x] Validate the bundle manifest, roles, checksums, identity, and caveats
  - [x] Read optional validation-report and model-card readiness evidence
  - [x] Add `fhops scenario hydrology validate`, tests, and docs
- [x] P15.2 Register and pin a hydrology bundle in a scenario (#220)
  - [x] Add the scenario pin and readiness fields
  - [x] Add idempotent registration and stale-manifest rejection
  - [x] Add `fhops scenario hydrology register`, tests, and docs
- [x] P15.3 Map FHOPS support to watersheds and receptors (#221)
  - [x] Define the explicit crosswalk and review metadata
  - [x] Enforce complete coverage or recorded gaps
  - [x] Add `fhops scenario hydrology map`, tests, and docs
- [x] P15.4 Load schedule-bound road/culvert exposure (#222)
  - [x] Consume the shared `ws4.hydrology.exposure.v1` contract
  - [x] Bind the table to one schedule hash and refuse missing/duplicate rows
  - [x] Add raw/derived features, tests, and docs
- [x] P15.5 Screen a schedule and gate on readiness (#223)
  - [x] Emit per-watershed/receptor/period rows and refusals
  - [x] Apply `allow_provisional`, `require_reviewed`, and `require_ready`
  - [x] Refuse fixed exposure in optimizer use and document the boundary
- [x] P15.6 Validate, document, and close out P15 (#224)
  - [x] Add the synthetic/public fixture and fail-closed matrix
  - [x] Update docs, roadmap, note, and changelog
  - [x] Write the closeout report and merge the phase PR (#232)

Acceptance:

- A valid bundle pins every required artifact by checksum and size.
- A scenario pin reloads only when the manifest and artifacts still match.
- Every in-scope support maps explicitly or records a gap.
- Exposure is reviewed and bound to one schedule.
- Screening emits deterministic rows and explicit refusals.
- Missing, unreviewed, or blocked evidence refuses.
- The fixture covers success and fail-closed paths.
- No real watershed or regulatory result is claimed.
- FHOPS quality suite and docs build are green.

Closeout: `notes/reports/p15-closeout.md`; final PR #232 merged as `3b404414`.

## Phase 16 — Flood-aware operational constraints — complete

Parent issue: #235. Branch: `feature/phase16-flood-operational-constraints`.

Goal: manage operational flood exposure against a fixed external hazard, not
optimize watershed flood response. FHOPS checks and constrains schedule activity
inside watch, warning, and closure windows by watershed and explicit assets.

Authoritative note: `notes/phase16_flood_operational_constraints.md`.
Closeout: pull request #255 squash-merged as `b850275d`; the phase report is
`notes/reports/p16-closeout.md`.

- [x] P16.1 Define and implement the operational hazard-window contract (#236)
  - [x] Validate schema, watershed ids, review metadata, day ranges, and overlaps
  - [x] Add severity lookup and validation report
  - [x] Add `fhops scenario hydrology hazard validate`, tests, and docs
- [x] P16.2 Load road/culvert asset evidence (#237)
  - [x] Define explicit asset ids, types, watersheds, and review metadata
  - [x] Reject unknown/duplicate assets without geometry inference
  - [x] Add tests and docs
- [x] P16.3 Check a schedule for hazard-window violations (#238)
  - [x] Map block activity to watersheds through the P15 crosswalk
  - [x] Emit watch/warning/closure events and closure violations
  - [x] Add the constraint-check CLI, CSV/JSON output, tests, and docs
- [x] P16.4 Integrate fixed hazard constraints where supported (#239)
  - [x] Audit solver decision variables for block/day/shift constraints
  - [x] Keep enforcement at the one-schedule check layer
  - [x] Record the missing shared solver hook and road-work timing limitation
- [x] P16.5 Prove, document, and close out P16 (#240)
  - [x] Add the synthetic/public fixture and fail-closed matrix
  - [x] Update docs, roadmap, note, and changelog
  - [x] Write the closeout report and queue the phase PR

Acceptance:

- Hazard windows and assets validate explicit ids and review metadata.
- A schedule reports watch, warning, and closure events.
- Closure activity fails by default; warning failure is an explicit policy.
- Missing evidence refuses.
- Solver integration, if present, is fixed-scenario only.
- No real watershed, flood map, or regulatory result is claimed.
- FHOPS quality suite and docs build are green.

## Phase 17 — Tree-scale inventory and spatial harvesting simulation — complete

Parent issue: #247. Branch: `feature/p17-tree-scale`.

Goal: consume a validated individual-tree inventory for FHOPS blocks, derive
stem-level volume and bucking, simulate one machine processing actual stems,
replay an existing schedule at tree scale, and export a deterministic 3D scene.
This is a tree-scale execution layer; the block/day MILP remains the planning
authority. FHOPS does not implement LiDAR segmentation.

Authoritative note: `notes/tree_scale_simulation_plan.md`.
Closeout: `notes/reports/p17-closeout.md`; final PR #275.

- [x] P17.1 Define tree inventory contract and synthetic fixture (#248)
  - [x] Record the tree-level data-source audit
  - [x] Define `fhops.tree.inventory.v1` and metadata
  - [x] Add validation, CLI, synthetic fixture, tests, and docs
- [x] P17.2 Pin inventory to scenario and build block tree maps (#249)
  - [x] Add the scenario reference and checksum validation
  - [x] Resolve trees to blocks and reconcile block evidence
  - [x] Add the map CLI, manifest, tests, and docs
- [x] P17.3 Derive stem volume and bucking (#250)
  - [x] Define the pluggable stem model
  - [x] Produce volume, logs, products, and block totals
  - [x] Add the CLI, synthetic model, tests, and docs
- [x] P17.4 Simulate one machine processing trees in one block (#251)
  - [x] Implement reach, terrain, and deterministic tree selection
  - [x] Emit per-tree cycle events and block totals
  - [x] Add the CLI, tests, and docs
- [x] P17.5 Replay an existing schedule at tree scale (#252)
  - [x] Drive the simulator from assignments
  - [x] Track tree consumption, leftovers, and discrepancies
  - [x] Add the replay CLI, manifest, tests, and docs
- [x] P17.6 Export a 3D scene and viewer (#253)
  - [x] Export deterministic glTF/GLB terrain, trees, paths, and logs
  - [x] Add LOD, viewer/import docs, and a camera path
  - [x] Add scene tests
- [x] P17.7 Validate, document, and close out P17 (#254)
  - [x] Add the end-to-end synthetic fixture and fail-closed matrix
  - [x] Run the quality suite and docs build
  - [x] Write the closeout report and queue the phase PR

Acceptance:

- A valid inventory loads and every tree resolves to one block.
- Unsafe contracts fail explicitly.
- Tree totals reconcile with block evidence or report a mismatch.
- One machine produces deterministic per-tree events.
- A schedule replay exposes leftovers and discrepancies.
- The 3D scene is deterministic and opens in a standard glTF viewer.
- No real tree map, operational decision, or regulatory claim is made.
- FHOPS quality suite and docs build are green.

> Phase 16 is a separately owned flood-aware operational phase and is not part
> of this branch. P17 does not modify its issue tree or scope.

## Phase 18 — Hydrology documentation and reproducibility — complete

Parent issue: #260. Branch: `feature/phase18-hydrology-docs`.

Goal: make the FEMIC → WS4 → FHOPS hydrology path reproducible for a new user.
This is documentation and reproducibility work, not a new hydrology capability.
P17 is the active tree-scale phase, so this phase uses P18.

Authoritative note: `notes/phase18_hydrology_docs_reproducibility.md`.
Closeout: pull request #276 squash-merged as `919a4fe0`; the phase report is
`notes/reports/p18-closeout.md`.

- [x] P18.1 Audit hydrology documentation and reproducibility gaps (#261)
  - [x] Inventory FEMIC, WS4, and FHOPS hydrology docs
  - [x] Record gaps, owners, and data/review blockers
  - [x] Separate documentation gaps from capability gaps
- [x] P18.2 Publish the pinned cross-repo quickstart (#262)
  - [x] Pin package versions and environment
  - [x] Run the synthetic FEMIC/WS4/FHOPS path
  - [x] Record expected outputs and unsupported steps
- [x] P18.3 Publish the contract and schema index (#263)
  - [x] List every hydrology, crosswalk, exposure, hazard, and asset contract
  - [x] Record required fields, ownership, and refusal behavior
- [x] P18.4 Add executable hydrology docs checks (#264)
  - [x] Check links and runnable snippets
  - [x] Run the synthetic quickstart in CI
- [x] P18.5 Close out the documentation phase (#265)
  - [x] Verify docs and gates
  - [x] Record synthetic/real-data limits and close out

Acceptance:

- Every gap has an owner.
- The quickstart names versions, fixtures, commands, and expected outputs.
- The contract index covers every schema in the workflow.
- Docs checks pass in CI.
- No new hydrology capability or real watershed result is claimed.

## Phase 19 — Nemora tree-inventory handoff

Parent issue: #300. Branch: `feature/phase19-nemora-handoff`. Status: complete. Plan:
`notes/phase19_nemora_handoff.md`.

Goal: prove that a Nemora-generated `fhops.tree.inventory.v1` fixture is
consumable by the released FHOPS tree-scale workflow without making Nemora a
runtime dependency.

- [x] P19.1 Generate and commit a Nemora tree-inventory fixture (#301)
  - [x] Generated a 40-tree deterministic synthetic table.
  - [x] Exported CSV/metadata with Nemora 0.1.0a1.
  - [x] FHOPS validates 40 trees/1 block/4 species; provenance recorded.
- [x] P19.2 Add the handoff scenario, docs, and end-to-end test (#302)
  - [x] Added B01/L1 scenario with a verified pin.
  - [x] Ran 40-tree system: 21.512 m³, 0 unreachable, no warnings.
  - [x] Added end-to-end test; no Nemora import.
- [x] P19.3 Close out and decide the release path (#303)
  - [x] Ran gates; two pre-existing HiGHS tests fail locally and are reported.
  - [x] Wrote `notes/reports/p19-closeout.md`.
  - [x] No 1.2.1 now; ship with next scheduled release.

## Phase 20 — Web serious game

Parent issue: #311. Branch: `feature/phase20-serious-game`. Status: active.
Plan: `notes/phase20_serious_game.md`.

Goal: turn the operational web UI into a deterministic instructor-run serious
game. Each level is one real VRI-derived stand from MKRF, AFRF Gavin Lake, or
AFRF Knife Creek. Teams choose a bounded machine/arrival/landing/bucking plan
and receive a 0–100 score based on normalized net operations profit, including
log-value recovery and operating costs.

The former Tiny7/Small21/Medium42/Large84 shift-scenario levels are retired
from P20. Their boundary/precompute code remains only while the stand-scale
loader replaces it.

- [ ] P20.1 Define stand levels, inventory/control contract, and precompute (#312)
  - [x] Selected one MKRF, one Gavin Lake, and one Knife Creek stand boundary.
  - [x] Committed EPSG:3005 GeoJSON boundaries and provenance catalog.
  - [ ] Generate pinned Nemora/PSP tree inventories; resolve CWHdm/ICHmk3 PSP.
    - [x] Knife Creek harvested/residual inventories generated and validated.
  - [ ] Define landing/road-extension assets, product prices, and bucking policy.
    - [x] Selection-cut careful-logging trade-off with decreasing damage benefits.
  - [x] KC stand-scale precompute: 20 combinations, best $75,705.63,
    worst $21,969.10.
  - [x] MKRF/Gavin PSP inventories and four-combination precomputes.
  - [x] Rebalance the synthetic Gavin deck to straddle break-even.
  - [ ] Add any remaining levels.
- [ ] P20.2 Implement the deterministic game engine, scoring, and session state (#313)
  - [x] Net-profit evaluator, price deck, and 0–100 normalization.
  - [x] One-play/order enforcement and local tournament persistence.
  - [x] Local game API: public level, session/team, ordered submission,
    leaderboard.
  - [ ] Add the Game workspace UI and level-map viewport.
- [ ] P20.3 Add the game API and web workspace (#314)
  - [x] Local API: level metadata, session/team, ordered submission, leaderboard.
  - [x] First `/game` shell: whole-stand SVG, controls, score, team join.
  - [x] Session progress and leaderboard panel.
  - [x] CLI flags for stand levels, precomputes, agent model, and cache.
  - [ ] Full lobby/level-map and live progress.
- [ ] P20.4 Prove fairness, document the tournament, and close out (#315)
  - [x] Deterministic/fairness/leakage tests.
  - [x] Instructor docs and validation note.
  - [ ] Full lobby/level-map/live-progress polish and final phase close-out.
- [ ] P20.5 Add the optimal-parameter learning debrief (#316)
  - [x] Facts and single-parameter counterfactual deltas.
  - [x] Deterministic template fallback with optional LLM hook.
  - [x] Post-level debrief API/UI and leakage tests.
  - [x] Connect the optional DeepSeek V4.1 Flash provider and level+choice cache.
  - [x] Final-only optional chat panel, gated by full tournament completion.

## Backlog & Ideas
- [x] Add the ground-based multi-machine tree-scale simulation (`fhops tree system`). Optional DEM/single-corridor road routing, calibrated skidder/loader rates, shift windows, roadside processing, and downstream truck/landing inventory are now wired in; full road-network routing, landing search, full road scale/landing search and adaptive truck dispatch remain follow-ups; a committed tree-system example is now packaged; small connected road-network routing is supported; per-machine processor specs are now supported; deterministic downtime, seeded breakdowns, loader-blocking truck dispatch, and shift-aware staggered truck arrivals are now implemented; multiple processors are now supported and the 2026-10-29 sensitivity check found the processor rate dominates the demo.
- [ ] Agentic tuner R&D (prompt loop, guardrails, benchmarking) — revisit once the conventional tuning suite and reporting pipeline are stable.
- [x] Integration with Nemora sampling outputs for downstream operations analytics (P19 tree-inventory handoff).
- [x] Scenario authoring UI and schema validators for web clients (P12.6, #183).
- [ ] Cloud execution harness for large-scale heuristics.
- [ ] DSS integration hooks (ArcGIS, QGIS) for geo-enabled workflows.
- [ ] Jaffray MASc thesis alignment checkpoints (`notes/thesis_alignment.md` TBD).
- [ ] VSCode keeps firing web apps on various random-sounding ports while running `injest_mip_baselines.py` and other benchmarking scripts? What is up with that? It is annoyingly resulting in VSCode interface popping up "Your application is running on port XXXX" messages (becaue of the built-in port-forwarding proxy).
- [ ] Schedule “full” analytics notebook runs (no light flag) on a less frequent cadence (nightly or weekly: leaning towards weekly) to guard against stochastic regression while keeping CI duration manageable.
  - [ ] Extend CI with a `cron` job that invokes `scripts/run_analytics_notebooks.py --timeout 900` (no `--light`) and publishes the resulting reports to the telemetry Pages bundle, keeping a 4-week artifact history for comparison.
- [ ] `pre-commit` autoupdate (especially `pre-commit-hooks`) plus workflow wiring so stage deprecation warnings are resolved before upstream removal.
- [x] Full `pre-commit run --all-files` notebook debt: cleaned/approved under issues #66–#70 so `main` CI publishes docs again.
- [ ] Post-Phase 6 validation scale-up: full 5-year/500+ block tactical benchmark, practitioner case validation, guided planner notebooks, and decomposition only if profiling shows a bottleneck.
- [ ] Hydrology optimizer integration: derive exposure per candidate schedule and gate it on reviewed evidence. Deferred until a route-state contract and a reviewed response surface exist.
- [ ] Dataset inspection + data-quality polish (see `notes/dataset_inspection_plan.md`)
  - [ ] Enforce/document 24 h/day machine availability in docs + sample datasets, and flag deviations via the inspector CLI.
