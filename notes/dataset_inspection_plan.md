# Dataset Inspection Plan

## Context
- Goal: ensure shipped datasets and synthetic-data generator parameters look realistic (no >10x deviations from domain expectations) prior to broad release.
- Driver: post-v0.1.0-a1 push to let developers/users inspect datasets via CLI before ingestion, preventing GIGO and aligning with FHOPS roadmap data-quality milestones.

## Conversation Snapshot (2025-02-??)
- We agreed to focus on dataset + synthetic generator parameter realism now that the release candidate is out.
- First concrete step is a CLI that compiles and dumps parameter summaries for any provided dataset; Python API can follow later.
- This inspection CLI is intended both for developers and “regular” users to validate newly created datasets.

## Working Assumptions / Decisions
- Inspect exactly one dataset per CLI invocation; batching will be layered on later via scripting.
- Shipped demo datasets can be referenced by canonical name; ad-hoc datasets use filesystem paths (need resolver that accepts either).
- Initial focus is per-element inspection (e.g., single machine/block) rather than whole dataset dumps; CLI should accept an element selector.
- Dataset-generator parameter inspection is deferred until after the core CLI is stable.
- CLI output should be human-readable tables in the terminal; machine-friendly JSON export can wait.
- First iteration only dumps raw input parameters gathered via existing schemas/contracts; missing or derived statistics are simply flagged as TODOs in the CLI output/planning doc.
- CLI must leverage the authoritative schemas/data contracts in code; flag any mismatch with planning docs.
- Element selection UI can be interactive: when the selector is incomplete, prompt step-by-step (system -> machine -> block, etc.).
- Sample datasets should assume 24-hour machine availability per day (consistent with year-round operations except brief spring shutdowns).

## Open Questions (awaiting product/UX decisions)
1. What future extensions do we need beyond raw parameters (e.g., derived statistics, anomaly detection)?
2. When we add machine-friendly output, should it be JSON, CSV, or something tied to internal tooling?
3. Which CLI UX patterns should we support besides interactive prompts (flags for non-interactive CI usage)?

## Next Steps
- Capture product answers to the open questions above.
- Design CLI UX + module layout once decisions land.
- Define how the interactive prompt workflow will operate (prompt text, validation, escape hatches).
- Hook into roadmap artifacts (e.g., `FHOPS_ROADMAP.md`) once scope is approved.

## Latest Progress
- Enforced 24 h/day defaults end-to-end: schema defaults flipped, shipped datasets refreshed, synthetic generator now exposes `machine_daily_hours`, and release/docs call out the assumption.
- Dataset inspector CLI grew `inspect-block`/`inspect-machine` commands plus non-24 h/day warnings to surface regressions immediately; roadmap + release notes capture the milestone.
- Documentation touchpoints (data contract + synthetic how-to) and release notes now reference the inspector warning and CLI override so users understand the new behavior.
- Scenario loader + synthetic generator now emit Lahrsen-based stand metrics (`avg_stem_size_m3`, etc.) and warn when blocks drift outside BC ranges; `fhops dataset` exposes commands to inspect these ranges interactively.
- Sample datasets now carry those stand metrics (seeded within Lahrsen ranges), reducing validator noise and giving users concrete examples of expected values.
- WS3’s PaCal + Monte Carlo backup logic needs to be ported so Lahrsen-style productivity/costing helpers can treat inputs as random variates (expected-value outputs) rather than deterministic means; capture this before we wire the costing helper.

## BC Productivity Model Insights (Lahrsen 2025 thesis)
- Dataset: 9,865 FPDat II production reports (filtered to 3,081 daily machine-level observations, 205 cutblocks) from 71 feller-bunchers across BC (Jan 2022–Jul 2024); covariates captured automatically: average stem size (0.09–1.32 m³/tree), average volume per hectare (75–856 m³/ha), stem density (205–3,044 trees/ha), ground slope (1.5–48.9%).
- Daily machine-level mixed-effects model (nested MachineID within BlockID) provides fixed-effect coefficients for productivity in m³/PMH15:  
  `Prod = 67.99*AvgStemSiz + 0.059*VolumePerH + 0.012*AvgStemDen - 0.461*AvgGroundS` (heteroscedastic best-fit; CI ranges roughly ±10%).  
  Stem size dominates (>+59 m³/PMH15 per +1 m³/tree), slope penalty ≈ −0.46 per +1%, density/volume effects smaller per unit but cover wide ranges.
- Cutblock-level linear model (aggregation) delivers similar structure with tighter CIs:  
  `Prod = 61.02*AvgStemSiz + 0.052*VolumePerH + 0.014*AvgStemDen - 0.24*AvgGroundS` (+ optional block-size term).  
  A heteroscedastic variant (random contractor effect) yields coefficients 57.08 / 0.031 / 0.003 / −0.36 / +0.013.
- Thesis also documents GNSS/coverage QA thresholds (≥70–90% coverage, <3 h GNSS gaps) and PMH15 error calibration (<1% with WTD 60–90 s + OTD), which we can reuse for data validation tooling.
- Parameter domains from the thesis give modern BC benchmarks for sample dataset defaults and synthetic generator ranges (piece size, densities, slopes, productivity).
- Snapshot of these ranges now lives in `src/fhops/productivity/_data/lahrsen2025_ranges.json` for validators/docs to consume.

## TODO Checklist
- [x] Update `Machine.daily_hours` default in the data contract to 24.0 so newly defined machines inherit round-the-clock availability.
- [x] Ensure synthetic dataset generator configs/sample overrides default to 24-hour machines (shift configs or CLI overrides may need alignment).
- [x] Sweep every shipped dataset (`examples/*/data/machines.csv`, regression fixtures, docs snippets) to set `daily_hours=24`.
- [x] Document the 24-hour assumption in data-contract/how-to docs and cross-link from the planning roadmap.
- [x] Extend the dataset inspector to flag machines with `daily_hours != 24` (warning first, enforcement later).
- [ ] Revisit mobilisation/production-rate assumptions once the 24-hour baseline is enforced.
- [ ] (Greg) Track down the original MRNF harvest-cost technical report cited in the Woodstock DLL, add it to the references library, and capture its equations for future machine-costing helpers.
- [ ] (Greg) Identify Canadian (BC-first, Canada-wide) machine productivity functions covering major systems/prescriptions, confirm licensing/IP constraints, and document which coefficients we can openly publish; defer US coverage until needed.
- [x] Extract structured Lahrsen 2025 parameter ranges (stem size, volume/ha, density, slope, productivity) into reusable config/validation tables and surface them in docs + schema validators.
- [x] Align FHOPS sample datasets + synthetic generator defaults with Lahrsen 2025 parameter ranges (piece size, volume/ha, density, slope, productivity) and document validation thresholds.
- [ ] Implement Lahrsen-based productivity helper (fixed-effect predictions + optional block-level adjustments) as interim baseline until new FPInnovations coefficients arrive.
- [ ] Document PMH/PMH15/SMH terminology consistently across how-to guides (e.g., evaluation, costing) once productivity helper/costing pipeline stabilises.
- [ ] Port WS3 random-variate handling (PaCal + Monte Carlo fallback) into the productivity/costing helpers so expected-value outputs behave correctly even when PaCal fails to converge.

## Rollout Plan (3-level work breakdown)

1. **CLI + Data Enhancements**
   1.1 Machine Inspector Expansion
       - Add mobilisation parameter output (walk cost, thresholds, setup/move costs) for each machine.
       - Surface utilisation/rental-rate interpretations (explicit $/SMH label, warn if missing).
       - Provide optional verbose mode to dump crew capabilities and future productivity defaults.
   1.2 Block/Scenario Context
       - Extend `inspect-block` with key derived stats (area, avg stem size, harvest system links).
       - Allow dataset-level summaries (counts, default assumptions) as scaffolding for aggregation later.
   1.3 Synthetic Generator Signals
       - Persist utilisation + rental rate defaults in synthetic configs/metadata.
       - Ensure CLI overrides propagate to metadata and inspector views for parity.

2. **Machine Costing Helper**
   2.1 Equation Port + Validation
       - Port WS3 harvest cost productivity/rental-rate equations into FHOPS helpers.
       - Reproduce spreadsheet/DLL outputs with unit tests seeded by Greg’s examples.
       - Add documentation referencing the MRNF report (pending retrieval).
   2.2 CLI/API Exposure
       - New command (`fhops dataset estimate-cost` or similar) that combines machine params, block attributes, and productivity functions to emit $/SMH and (optionally) $/m³.
       - Provide templates/config files so users can define custom machine systems.
   2.3 Evaluation Integration
       - Hook helper into playback/KPI modules to compute $/m³ post-hoc using actual assignments.
       - Emit warnings when solver inputs (rental rates, utilisation) are missing but evaluation needs them.

3. **References, Docs, and Governance**
   3.1 Source Document Capture (Greg)
       - Locate MRNF harvest-cost tech report, archive in `notes/` or `docs/reference/`, and cite it in planning docs.
       - Record provenance for productivity equations and any calibration constants.
   3.2 Documentation Updates
       - Expand data-contract/how-to sections with rental-rate workflow, machine costing helper usage, and CLI examples.
       - Add evaluation guide section on interpreting $/SMH vs. $/m³ outputs.
   3.3 Roadmap & Release Tracking
       - Reflect the rollout stages in `FHOPS_ROADMAP.md` and release notes once milestones land.
       - Define QA checkpoints (inspection CLI regression, cost-helper parity tests, doc updates) before public release.

## Proposed Next Steps
1. **Ingest Lahrsen coefficients**
   - Encode daily machine-level fixed-effect equations in a new helper module, expose via CLI (`fhops dataset estimate-productivity`) using block attributes (stem size, volume/ha, density, slope).
   - Validate our implementation by recreating Lahrsen’s heteroscedastic predictions on a sampled dataset (unit tests comparing to published coefficients/CIs).
   - Extract the observed parameter ranges from Lahrsen 2025 into a machine-readable table (JSON/YAML) and hook them into schema validation + docs so future tasks can reuse them.
2. **Update dataset defaults**
   - Rewrite sample dataset JSON/CSV templates and synthetic generator distributions to fall within Lahrsen-observed ranges; add validation rules rejecting out-of-band values unless explicitly overridden.
3. **Plan costing workflow**
   - Combine the productivity helper with machine rental-rate inputs (in $/SMH) to produce BC-calibrated $/m³ estimates downstream in evaluation scripts; document how this links to the forthcoming machine-costing CLI.
