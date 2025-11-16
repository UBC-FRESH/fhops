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
- Initial costing helper CLI is in place: `fhops dataset estimate-cost` pairs Lahrsen productivity (deterministic or RV) with rental rates/utilisation to emit $/m³.
- Candidate productivity models for single-grip harvesters/harwarders identified via Arnvik (2024) review (2013–2023 literature); next step is selecting/porting BC-appropriate regressions for those roles.
- Appendix 8 tables from Arnvik (2024) exported (per-page CSVs + aggregate raw dump) via `scripts/extract_arnvik_models.py`; next step is normalising the rows into the productivity registry schema.
- Appendix 8 extraction now targets the true section pages (101–116) so the aggregated CSV is clean; `scripts/build_productivity_registry.py` now preserves publication context when only the model rows are present, boosting coverage to 357 parsed models (still missing the last ~65 rows—likely other machine families that Arnvik references but aren’t captured by the current tables). Preliminary counts from Table 9 (in the thesis) suggest we still need to ingest forwarder, grapple-skidder, shovel logger, yarder, and helicopter models.
- Appendices 9–11 are now machine-readable: `scripts/parse_arnvik_{variables,parameters,statistics}.py` stream text directly from the PDF to capture variable definitions, per-model coefficients (a–t), and observational metadata (OB, observations, structure, R², significance, F). These JSONs (`notes/reference/arnvik_tables/appendix{9,10,11}/*.json`) power the registry builder/validator.
- Machine-type labels coming out of Appendix 8 are now harmonised against FHOPS roles (e.g., `H` → `single_grip_harvester`, `FB` → `feller_buncher`, `HW` → `harwarder`), giving us immediate visibility into roles we already cover vs. gaps (harwarder, skidder_harvester) that need BC productivity functions + system support.
- Added a Camelot-based extractor (`scripts/extract_arnvik_models_camelot.py`) that reads the Appendix 8 tables directly from the PDF using a tuned table region; it now normalises `(author, model, HM, machine, base, propulsion, DV, units, formula)` rows for pages 101–116 and produces a dedicated aggregate CSV for downstream tooling.
- `scripts/build_productivity_registry.py` can ingest the Camelot aggregate, fall back to the legacy pdfplumber rows for any gaps, and now builds 392 enriched models (up from 109) covering harvesters, feller-bunchers, harwarders, and skidder-harvesters. Machine labels are harmonised (no more `fb_sim__pb` artefacts), and the builder automatically backfills missing formulas/units from the legacy source.
- Current machine-type coverage from Arnvik (Camelot + legacy): 260 `single_grip_harvester`, 94 `feller_buncher`, 14 `feller_buncher_sim`, 8 `harwarder`, 6 `single_grip_harvester_sim`, 5 `skidder_harvester`, 5 `feller_buncher_drive_to_tree`. No forwarders/grapple skidders yet – these are the next extraction targets.

### Arnvik Machine Coverage Snapshot

| Machine family (normalized) | Models |
| --- | --- |
| `single_grip_harvester` | 260 |
| `single_grip_harvester_sim` | 6 |
| `feller_buncher` | 94 |
| `feller_buncher_sim` | 14 |
| `feller_buncher_drive_to_tree` | 5 |
| `harwarder` | 8 |
| `skidder_harvester` | 5 |

Covered FHOPS roles: `single_grip_harvester`, `feller-buncher`, `harwarder`, `skidder_harvester`. Missing FHOPS roles: `forwarder`, `grapple_skidder`, `shovel_logger`, `roadside_processor`, `loader`, `grapple_yarder`, `skyline_yarder`, `helicopter_longline`, `tethered_harvester`, `tethered_shovel_or_skidder`, `hand_faller`, etc. Candidate references mentioned in Arnvik’s literature appendix for these gaps include Eriksson & Lindroos (2014), Laitila & Väätäinen (2014, 2020), Han et al. (2018), and various yarder cost/productivity studies cited in Appendix 1 – need to mine these next.

### FHOPS Machine Role Coverage Matrix

| FHOPS role | Arnvik coverage? | Candidate references / notes |
| --- | --- | --- |
| single_grip_harvester | ✅ 260 models (CTL harvester variants) | Appendix 8 (pages 101–115) already ingested. |
| feller-buncher (swing-boom + DTT) | ✅ 94 SB models + 5 DTT variants | Appendix 8 (FT FB rows). |
| feller-buncher_sim | ✅ 14 | Simulation models – treat as optional. |
| harwarder | ✅ 8 | CTL harwarder entries captured; need BC calibration later. |
| skidder_harvester | ✅ 5 | Appendix 8 CTL skidder-harvester; check if applicable to BC ground-based systems. |
| forwarder | ❌ | Eriksson & Lindroos (2014), Laitila & Väätäinen (2014, 2020); FPDat forwarder datasets. |
| grapple_skidder | ❌ | Han et al. (2018), George et al. (2022), FPInnovations skidder studies. |
| shovel_logger | ❌ | BC shovel logging time studies (FPInnovations tech transfer notes). |
| loader | ❌ | Derive from equipment catalogs or FPDat cycle-time data. |
| roadside_processor / landing processor | ❌ | Need landing processor regressions (e.g., Labelle et al. 2016/2018). |
| grapple_yarder / skyline_yarder | ❌ | Aubuchon (1982), Böhm & Kanzian (2023) references; no Appendix 8 coverage. |
| tethered_harvester | ❌ (Lahrsen covers but not Arnvik) | Use Lahrsen BC FPDat data + WS3 RV logic. |
| tethered_shovel_or_skidder | ❌ | Winch-assist operations: mine FPInnovations trials. |
| helicopter_longline / loader_or_water | ❌ | See Arnvik Appendix 1 (helicopter references) + FPInnovations helicopter cost modules. |
| hand_faller / hand_or_mech_faller | ❌ | Manual falling regressions (historical BC/Quebec studies). |
- Appendix references are now parsed via `scripts/parse_arnvik_references.py`, producing `notes/reference/arnvik_tables/references.json` and letting the registry tag each model with its original citation for provenance checks.
- Appendix 8 in Arnvik (2024) lists 422 productivity models (harvesters, feller-bunchers, harwarders). Need to digitise into a searchable registry (machine type, region, system, predictors, coefficients, R², etc.) so we can plug gaps for the remaining machine roles.

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
- [ ] Source BC productivity functions (or build new regressions) for every machine role in the harvest system registry so the costing helper can cover entire systems, not just feller bunchers:
  - [x] feller-buncher (Lahrsen 2025 + Arnvik Appendix 8 models already ingested)
  - [x] single_grip_harvester (Arnvik Appendix 8 models ingested via Camelot)
  - [ ] forwarder *(not covered in Appendix 8 – need to mine Eriksson & Lindroos 2014, Laitila & Väätäinen 2014/2020, and FPInnovations datasets for CTL forwarding regressions)*
  - [ ] grapple_skidder *(seek sources such as Han et al. 2018, George et al. 2022 for grapple-skidder cycle-time models)*
  - [ ] shovel_logger *(likely only in regional studies; consider mining FPInnovations yarding/cable literature or BC-specific shovel logging time studies)*
  - [ ] loader *(loader productivity/cycle-time functions absent; may be simple derived metrics but need references)*
  - [ ] roadside_processor / landing_processor_or_hand_buck *(some harvester-side processing models exist; need explicit landing processor regressions)*
  - [ ] grapple_yarder / skyline_yarder *(no Appendix 8 coverage; look to Aubuchon 1982, Böhm & Kanzian 2023 review)
  - [ ] tethered_harvester *(Lahrsen-based BC data partially covers this; need explicit tethered winch assist productivity functions)*
  - [ ] tethered_shovel_or_skidder *(same as above)*
  - [ ] helicopter_longline / loader_or_water *(Arnvik cites helicopter productivity literature – extract those)*
  - [ ] hand_faller / hand_or_mech_faller / hand_buck_or_processor *(Appendix 8 lacks manual falling models; rely on FPInnovations / historical time studies)*
- [ ] Digitise Arnvik 2024 Appendix 8 productivity catalog (harvesters, feller-bunchers, harwarders) into a structured registry (CSV/JSON) keyed by machine type, harvesting system, region, predictors, coefficients, R². Plan includes:
  - [ ] Extraction strategy: attempt Tabula/pandas parsing; if automated extraction fails due to formatting, fall back to semi-manual OCR or direct data entry.
  - [ ] Registry design: schema capturing publication metadata, machine type, harvest system, predictors, mathematical form, coefficients, fit metrics.
  - [ ] Ingestion pipeline: scripts to clean/normalise extracted rows (e.g., map machine type labels to FHOPS roles, convert units, note site conditions).
  - [x] Capture Arnvik (2024) bibliography as structured JSON (`notes/reference/arnvik_tables/references.json`) and plumb it into the productivity registry so every model records its citation provenance.
  - [x] Lock Appendix 8 page ranges to 101–116 and update the registry builder so it parses those tables into structured rows (currently 357 models with coefficients/statistics wired in, + citation metadata).
  - [x] Parse Appendix 9 variable definitions into JSON and attach units/descriptions to predictor codes.
  - [x] Parse Appendix 10 parameters + Appendix 11 statistical metadata straight from the PDF (text parsing to avoid CSV artefacts) and feed them into the registry builder so every model includes coefficients, OB context, R², significance, and F statistics.
  - [ ] Extend Appendix 8 extraction to the remaining machine tables (forwarders, grapple skidders, shovel/shovel loggers, yarders, helicopters, etc.), targeting ~422 total models, and update role mappings accordingly.
    - [ ] Confirm exact page ranges for each missing machine family (scan PDF for “Forwarder”, “Skidder”, “Yarder”, etc.) so extractor can be extended deterministically.
    - [ ] If tables are embedded in multi-column layouts (or appendices 7/8 supplements), prototype a fallback parser (camelot/tabula, or manual CSV transcription) to avoid silent data loss.
    - [x] Finish normalising the Camelot output so each row yields `(author, model, HM, machine, base, propulsion, DV, units, formula)` even when Camelot merges/splits the author/model cells; once stable, flip the registry builder to ingest the Camelot aggregate instead of the noisier pdfplumber CSV (done – builder now merges Camelot + legacy rows for 392 models).
    - [ ] Map remaining machine families referenced in Table 9 (forwarder, grapple skidder, shovel logger, yarder, helicopter) to FHOPS machine roles, and flag which ones still lack regression coverage in the registry.
  - [ ] Add validation (unit tests or checksum scripts) that fail if the extracted model count, predictor metadata, or coefficient sets drift from the expected totals.

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
