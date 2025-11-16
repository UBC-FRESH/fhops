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
+ [ ] Candidate productivity models for single-grip harvesters/harwarders identified via Arnvik (2024) review (2013–2023 literature); next step is selecting/porting BC-appropriate regressions for those roles.
+ [x] Appendix 8 tables from Arnvik (2024) exported (per-page CSVs + aggregate raw dump) via `scripts/extract_arnvik_models.py`; next step is normalising the rows into the productivity registry schema.
+ [x] Appendix 8 extraction now targets the true section pages (101–116) so the aggregated CSV is clean; `scripts/build_productivity_registry.py` now preserves publication context when only the model rows are present, boosting coverage to 357 parsed models (still missing the last ~65 rows—likely other machine families that Arnvik references but aren’t captured by the current tables). Preliminary counts from Table 9 (in the thesis) suggest we still need to ingest forwarder, grapple-skidder, shovel logger, yarder, and helicopter models.
+ [x] Appendices 9–11 are now machine-readable: `scripts/parse_arnvik_{variables,parameters,statistics}.py` stream text directly from the PDF to capture variable definitions, per-model coefficients (a–t), and observational metadata (OB, observations, structure, R², significance, F). These JSONs (`notes/reference/arnvik_tables/appendix{9,10,11}/*.json`) power the registry builder/validator.
+ [x] Machine-type labels coming out of Appendix 8 are now harmonised against FHOPS roles (e.g., `H` → `single_grip_harvester`, `FB` → `feller_buncher`, `HW` → `harwarder`), giving us immediate visibility into roles we already cover vs. gaps (harwarder, skidder_harvester) that need BC productivity functions + system support.
+ [x] Added a Camelot-based extractor (`scripts/extract_arnvik_models_camelot.py`) that reads the Appendix 8 tables directly from the PDF using a tuned table region; it now normalises `(author, model, HM, machine, base, propulsion, DV, units, formula)` rows for pages 101–116 and produces a dedicated aggregate CSV for downstream tooling.
+ [x] `scripts/build_productivity_registry.py` can ingest the Camelot aggregate, fall back to the legacy pdfplumber rows for any gaps, and now builds 392 enriched models (up from 109) covering harvesters, feller-bunchers, harwarders, and skidder-harvesters. Machine labels are harmonised (no more `fb_sim__pb` artefacts), and the builder automatically backfills missing formulas/units from the legacy source.
+ [x] Added `scripts/parse_arnvik_table9.py` so Table 9 (machine types vs. dependent-variable counts) lives in `notes/reference/arnvik_tables/table9_machine_counts.csv`, making it easier to measure how far we are from Arnvik’s reported 422-model inventory.
+ [x] Added `scripts/extract_arnvik_appendix45.py`, which uses Camelot to dump Appendix 4 (machine specs) and Appendix 5 (stand/operator descriptions) into raw CSVs (`appendix4_machines.csv`, `appendix5_stands.csv`). These need further normalization (e.g., splitting N/HM fields, parsing machine/head models, debarking flags), but the source data is now machine-readable.
- Implemented the Stoilov et al. (2021) skidder-harvester equations (delay-free and with-delays) as FHOPS helpers so `skidder_harvester` now has a baseline productivity model.
- Implemented the Laitila & Väätäinen (2020) brushwood harwarder equations (Eq. 1–7) as `fhops.productivity.laitila2020.estimate_brushwood_harwarder_productivity`; unit tests (`tests/test_laitila2020.py`) recreate the published 6.5–8.4 m³/PMH curves across forwarding distances.
- Added the Ghaffariyan et al. (2019) thinning forwarder models (small 14 t and large 20 t variants) as `fhops.productivity.ghaffariyan2019`, with regression tests matching Table 4 productivity values and optional slope multipliers for >10% trails.
- Captured the Kellogg & Bettinger (1994) CTL multi-product forwarder regression (`fhops.productivity.kellogg_bettinger1994`) so mixed/saw/pulp scenarios with explicit travel components can be estimated; tests mirror Table 8 productivity numbers.
- Added Sessions & Boston (2006) shovel-logging helper (`fhops.productivity.sessions2006`) so we can inspect road-spacing trade-offs (productivity, cost/tonne, profit). Regression tests replicate the published 4-pass scenario.
- Added Spinelli et al. (2017) excavator-based grapple yarder regression (`fhops.productivity.spinelli2017`) as an interim surrogate for the requested grapple-skidder model; still need Han & George field equations once available.
- Added Visser et al. (2025) mechanical feeding study (CroJFE) to quantify shovel-assist productivity (25–100 m³/h), utilization (61%), and time-use splits for excavator feeders on NZ steep ground – informs combined shovel/yarder modeling, plus extracted cycle stats (loading 36–107 s, feeding 15–26 s, waiting 15–74 s) showing waiting ≈40% of feeding time and the dominant effect of mean piece size (0.5–3.5 m³).
- Logged McNeel (2000) longline yarding regression (Journal of Forest Engineering) covering coastal BC systems plus piece-size/line-length effects; key source for grapple yarder helper calibration (elemental regressions like Outhaul = 0.365 + 0.001576·Dist, Choke = 3.005 + 0.0805·LatDist, Unhook = 0.572 + 0.109·Pieces, and total-cycle `TC = 10.167 + 0.00490·Dist + 0.01836·Vdist – 0.01108·(Z1·Vdist) + 0.0805·LatDist + 0.1095·Pieces – 1.18·Z1`).
- Captured West, Sessions & Strimbu (2022) winch-assist + swing yarder steep slope system model (Forests 13:305) for integrated cut-to-length/long-log comparisons up to 115 cm DBH on 30–60% slopes, including their unified stemwise (Eq. 1) and roundtrip (Eq. 2) formulations (per-stem move time + quadratic volume terms; segmented loaded/unloaded travel speeds with slope/traction limits).
- Added Conor Bell (2017) OpCost thesis (Univ. of Idaho) describing the development/validation of USFS OpCost machine-rate model—primary reference for upcoming costing helper inputs (Miyata-style depreciation/utilization/wage components + business overhead and contractor-survey validation).
- Extracted OpCost input schema (Table 2.4) + cost workflow: 35 stand-level descriptors feed per-machine time models, then PMH → $/acre through machine rates built from fixed + variable owning/operating costs (Matthews 1942) with default PNW rates from Dodson et al. (2015); future costing helper will need a similar machine-rate table plus utilization/move-in handling. Dodson et al. provide per-machine assumptions (life 5 yrs, salvage 15–30%, utilization 60–90%, repair 75–100%, 6.5% interest, fuel $3.50/gal ≈ USD 0.92/L) and hourly rates (USD) averaged across Montana dealers—for BC work we’ll convert at ~1.33 CAD/USD (Bank of Canada 2024 avg) and bump diesel to ~CAD 1.80/L (~USD 1.35/L) to reflect higher Canadian fuel prices. Example conversions: feller-buncher ≈$149→$198 CAD/SMH (≈$249→$331 CAD/PMH); skidder $121→$161 CAD/SMH ($152→$202 CAD/PMH); processor $150→$200 CAD/SMH ($166→$221 CAD/PMH); stroke delimber $160→$213 CAD/SMH ($177→$235 CAD/PMH); loader $105→$140 CAD/SMH ($162→$215 CAD/PMH). FPInnovations Advantage Vol. 4 No. 23 repair/maintenance survey is benchmarked in 2002 CAD; Statistics Canada Machinery & Equipment CPI (Table 18-10-0005-01) gives a 2002→2024 cumulative factor of ≈1.56, so all FPInnovations R&M dollars now use that multiplier when we populate `data/machine_rates.json`.
- Archived Chad Renzie (2006) UNBC thesis comparing partial cut vs clearcut productivity/cost in cedar-hemlock stands (east-central BC); provides partial-cut machine-rate data for future scenario defaults (ground-based clearcuts $10.95–15.96/m³, group selection $16.09–16.93/m³, group retention $13.39/m³, cable clearcut $15.70/m³; mechanized felling increased residual damage while grapple skidding reduced skidding wounds vs line skidding).
- Imported Onuma (1988) Japanese review of North American time/cost analysis (森利研 誌) summarizing standard North American time-study/cost accounting methods—good methodological reference for our analytics pipeline (time-and-motion accounting + Miyata-style costing comparisons).
- Added Hartley & Han (2007) “Effects of Alternative Silvicultural Treatments on Cable Harvesting Productivity and Cost in Western Washington” (WJAF 22:204–212); contains detailed delay-free regression models + machine rates for skyline systems in clearcut, two-age, patch cut/thin, and group selection prescriptions (yarding costs $37–77 USD/mbf → ~$49–102 CAD/mbf at 1.33 FX, cycle-time deltas between chokers vs grapple carriages), giving us US Pacific Northwest partial-cut cable benchmarks.
- Added Böhm & Kanzian (2023) “A review on cable yarding operation performance and its assessment” (IJFE 34:229–253); consolidates global yarder productivity studies, key cost drivers (slope, road spacing, carriage type, payload, skyline geometry), and measurement/assessment methods—useful as a literature roadmap + sanity check for the grapple-yarders we’re encoding.
- Added Visser & Spinelli (2012) “Determining the shape of the productivity function for mechanized felling and felling-processing” (J. Forest Research 17:397–402); quantifies the “piece-size law” and shows productivity peaking at an optimum stem size (four NZ/Italy datasets) – informs mechanized feller/processor curves and highlights how productivity drops gracefully beyond the optimal piece size.
- Noted that “Effects_of_Alternative_Silvicu.pdf” is DRM-protected; need an accessible copy before we can extract silviculture productivity impacts.
- `fhops dataset estimate-forwarder-productivity` now exposes both sets of forwarder regressions (Ghaffariyan small/large + Kellogg saw/pulp/mixed) with parameter validation and Typer tests, so users can query productivity without writing Python.
- Reviewed the new machine-productivity PDFs (Di Fulvio 2024, Eriksson & Lindroos 2014, Kellogg & Bettinger 1994, McNeel & Rutherford, Ghaffariyan et al. 2019, Stoilov et al. 2021, Laitila & Väätäinen 2020, Berry 2019, Lee et al. 2018, Ünver-Okan 2020, Spinelli et al. 2016). These cover forwarders, grapple skidders/shovel loggers, processors/landing ops, brushwood harwarders, small cable yarders, coppice harvesters, etc.—none appear in Arnvik Appendix 8, so we must ingest them manually to close the FHOPS machine-role gaps.
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

Quick comparison to Arnvik Table 9 (`scripts/parse_arnvik_table9.py`) shows why we still fall short of the stated 422 models: Table 9 only enumerates CTL harvesters, harwarders, skidder-harvesters, and full-tree feller-bunchers. Forwarders, grapple skidders, yarders, etc. never appear in Appendix 8 – so we must gather those regressions directly from the underlying literature (Appendix 1 references, FPInnovations datasets, etc.) rather than expecting them to show up in the official model tables.

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

Ad hoc notes (TODO: process these leads and pull into planning docs):

- Di Fulvio et al. 2024 – global benchmarking (harvester, forwarder, skidder costs) for plantations.
- Eriksson & Lindroos 2014 – forwarder + harvester models (700 machines, Sweden).
- Kellogg & Bettinger 1994 / McNeel & Rutherford – CTL thinnings + selection harvest harvester/forwarder productivity.
- Ghaffariyan et al. 2019 – Australian thinning productivity (ALPACA database) for harvester/forwarder.
- Stoilov et al. 2021 – combined skidder-harvester (HSM 805 ZL + Woody 50) models.
- Berry 2019 – processor productivity (Kinleith NZ) for roadside processors.
- Lee et al. 2018, Ünver-Okan 2020 – small cable yarder + tractor winch productivity.
- Laitila & Väätäinen 2020 – brushwood harwarder & clearing productivity.
- Spinelli et al. 2016 – coppice harvesting meta-analysis (excavator-based harvesters, farm tractors).

Ad hoc notes (TODO: process these leads and pull into planning docs):

- 

### Next Actions for Missing Machine Families

1. **Forwarder** – Pull regressions from Eriksson & Lindroos (2014) and Laitila & Väätäinen (2014, 2020); capture predictor definitions and coefficients so CTL forwarder jobs (`forwarder`) get baseline productivity models.
2. **Grapple Skidder / Shovel Logger** – Mine Han et al. (2018), George et al. (2022), and FPInnovations skidder/shovel logging studies for grapple-skidder cycle-time equations.
3. **Yarder / Helicopter** – Use Aubuchon (1982) and Böhm & Kanzian (2023) to seed skyline/grapple yarder regressions, plus the helicopter references Arnvik cites.
4. **Processor / Loader** – Extract landing processor/log loader models (e.g., Labelle et al. 2016/2018, FPDat loader datasets) so `roadside_processor` and `loader` roles have coverage.
5. **Tethered systems** – Build interim regressions from Lahrsen’s BC tethered FPDat data for `tethered_harvester` and `tethered_shovel_or_skidder`, then validate against any published winch-assist studies.
6. **Manual operations** – Locate BC/Quebec hand-falling time studies to cover `hand_faller`, `hand_or_mech_faller`, and `hand_buck_or_processor` jobs.
7. **Appendix 4/5 normalization** – Parse the new raw CSVs into structured schemas (machine specs per publication/model, stand/operator metadata), then attach the relevant snippets to each registry entry so we can report machine model defaults and stand/operator context in the CLI.
8. **Appendix 7 abbreviations** – Ingest DV abbreviations into a dictionary so CLI output can show human-friendly descriptions for PV/PW/TV/TW/TU/etc.
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
[x] Update `Machine.daily_hours` default in the data contract to 24.0 so newly defined machines inherit round-the-clock availability.
[x] Ensure synthetic dataset generator configs/sample overrides default to 24-hour machines (shift configs or CLI overrides may need alignment).
[x] Sweep every shipped dataset (`examples/*/data/machines.csv`, regression fixtures, docs snippets) to set `daily_hours=24`.
[x] Document the 24-hour assumption in data-contract/how-to docs and cross-link from the planning roadmap.
[x] Extend the dataset inspector to flag machines with `daily_hours != 24` (warning first, enforcement later).
[ ] Revisit mobilisation/production-rate assumptions once the 24-hour baseline is enforced.
[ ] (Greg) Track down the original MRNF harvest-cost technical report cited in the Woodstock DLL, add it to the references library, and capture its equations for future machine-costing helpers.
[ ] (Greg) Identify Canadian (BC-first, Canada-wide) machine productivity functions covering major systems/prescriptions, confirm licensing/IP constraints, and document which coefficients we can openly publish; defer US coverage until needed.
[x] Extract structured Lahrsen 2025 parameter ranges (stem size, volume/ha, density, slope, productivity) into reusable config/validation tables and surface them in docs + schema validators.
[x] Align FHOPS sample datasets + synthetic generator defaults with Lahrsen 2025 parameter ranges (piece size, volume/ha, density, slope, productivity) and document validation thresholds.
[ ] Implement Lahrsen-based productivity helper (fixed-effect predictions + optional block-level adjustments) as interim baseline until new FPInnovations coefficients arrive.
[ ] Document PMH/PMH15/SMH terminology consistently across how-to guides (e.g., evaluation, costing) once productivity helper/costing pipeline stabilises.
[ ] Port WS3 random-variate handling (PaCal + Monte Carlo fallback) into the productivity/costing helpers so expected-value outputs behave correctly even when PaCal fails to converge.
[ ] Source BC productivity functions (or build new regressions) for every machine role in the harvest system registry so the costing helper can cover entire systems, not just feller bunchers:
  [x] feller-buncher (Lahrsen 2025 + Arnvik Appendix 8 models already ingested)
  [x] single_grip_harvester (Arnvik Appendix 8 models ingested via Camelot)
  [x] forwarder *(implemented baseline Eriksson & Lindroos 2014 model for CTL operations; still need to ingest Laitila & Väätäinen + FPInnovations variants for brushwood/southern conditions)*
  [ ] grapple_skidder *(seek sources such as Han et al. 2018, George et al. 2022 for grapple-skidder cycle-time models)*
  [ ] shovel_logger *(likely only in regional studies; consider mining FPInnovations yarding/cable literature or BC-specific shovel logging time studies)*
  [ ] loader *(loader productivity/cycle-time functions absent; may be simple derived metrics but need references)*
  [ ] roadside_processor / landing_processor_or_hand_buck *(some harvester-side processing models exist; need explicit landing processor regressions)*
  [ ] grapple_yarder / skyline_yarder *(no Appendix 8 coverage; look to Aubuchon 1982, Böhm & Kanzian 2023 review)
  [ ] tethered_harvester *(Lahrsen-based BC data partially covers this; need explicit tethered winch assist productivity functions)*
  [ ] tethered_shovel_or_skidder *(same as above)*
  [ ] helicopter_longline / loader_or_water *(Arnvik cites helicopter productivity literature – extract those)*
  [ ] hand_faller / hand_or_mech_faller / hand_buck_or_processor *(Appendix 8 lacks manual falling models; rely on FPInnovations / historical time studies)*
[ ] Digitise Arnvik 2024 Appendix 8 productivity catalog (harvesters, feller-bunchers, harwarders) into a structured registry (CSV/JSON) keyed by machine type, harvesting system, region, predictors, coefficients, R². Plan includes:
  [ ] Extraction strategy: attempt Tabula/pandas parsing; if automated extraction fails due to formatting, fall back to semi-manual OCR or direct data entry.
  [ ] Registry design: schema capturing publication metadata, machine type, harvest system, predictors, mathematical form, coefficients, fit metrics.
  [ ] Ingestion pipeline: scripts to clean/normalise extracted rows (e.g., map machine type labels to FHOPS roles, convert units, note site conditions).
  [x] Capture Arnvik (2024) bibliography as structured JSON (`notes/reference/arnvik_tables/references.json`) and plumb it into the productivity registry so every model records its citation provenance.
  [x] Lock Appendix 8 page ranges to 101–116 and update the registry builder so it parses those tables into structured rows (currently 357 models with coefficients/statistics wired in, + citation metadata).
  [x] Parse Appendix 9 variable definitions into JSON and attach units/descriptions to predictor codes.
  [x] Parse Appendix 10 parameters + Appendix 11 statistical metadata straight from the PDF (text parsing to avoid CSV artefacts) and feed them into the registry builder so every model includes coefficients, OB context, R², significance, and F statistics.
  [ ] Extend Appendix 8 extraction to the remaining machine tables (forwarders, grapple skidders, shovel/shovel loggers, yarders, helicopters, etc.), targeting ~422 total models, and update role mappings accordingly.
    [ ] Confirm exact page ranges for each missing machine family (scan PDF for “Forwarder”, “Skidder”, “Yarder”, etc.) so extractor can be extended deterministically.
    [ ] If tables are embedded in multi-column layouts (or appendices 7/8 supplements), prototype a fallback parser (camelot/tabula, or manual CSV transcription) to avoid silent data loss.
    [x] Finish normalising the Camelot output so each row yields `(author, model, HM, machine, base, propulsion, DV, units, formula)` even when Camelot merges/splits the author/model cells; once stable, flip the registry builder to ingest the Camelot aggregate instead of the noisier pdfplumber CSV (done – builder now merges Camelot + legacy rows for 392 models).
    [ ] Map remaining machine families referenced in Table 9 (forwarder, grapple skidder, shovel logger, yarder, helicopter) to FHOPS machine roles, and flag which ones still lack regression coverage in the registry.
  [ ] Add validation (unit tests or checksum scripts) that fail if the extracted model count, predictor metadata, or coefficient sets drift from the expected totals.

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
- **FPInnovations reference batch catalogued**
   - `notes/fpinnovations_reference_log.md` now covers the Advantage, Special Report, Handbook, Technical Report, Field/Forest Note, and cable-yard (FNCY) series (all but the OCR-stubborn FNCY14). High-priority sources for the registry/costing helper include SR54 & TR75 (coastal grapple yarders), TR119/TR125 (skyline + partial-cut productivity/cost), TR106/TR108 (interior CTL vs. tree-length systems), TR2016N46 (modern winch-assist harvester), SR89/TR103 (steep-slope ground skidding + soil-disturbance mitigation), HB12 (system catalog), and SR49/SR85 (equipment planning + partial-cut comparisons). TR112/TR127 regressions aren’t extractable from the available scans, so skyline coverage will rely on alternative references (e.g., Ünver-Okan 2020, Lee et al. 2018) until better copies surface. Next action: mine the remaining reports and integrate alternative skyline/tethered regressions so grapple skidders/yarders, skyline partial cuts, tethered felling, and steep-slope skidders enter the registry without waiting on new field campaigns.
- **BC grapple yarder helpers implemented**
   - Added `fhops.productivity.grapple_bc` exposing SR54 (Washington 118A bunched) and TR75 (Madill 084, bunched vs. hand-felled) productivity equations and registered pytest coverage. These regressions now replace the plantation-derived Spinelli placeholder when estimating CTL grapple productivity; next follow-up is to wire them into the registry metadata and costing helper plus extend coverage with TR112/TR127 skyline data.

## Immediate Next Tasks (queue)
- Extract grapple yarder/skidder regressions from SR54, TR75, TR112, and TR127 (turn length vs. payload) so we can replace the interim Spinelli yarder placeholder; only chase Han & George if BC/FPInnovations coverage still has gaps.
- Expand Appendix 4/5 normalization to capture operator, machine weight, slope/payload applicability so the FPInnovations datasets map cleanly into the registry schema.
- Pull skyline/tethered/partial-cut coefficients from TR119, TR125, TR2016N46, SR85, and HB12; keep Visser/McNeel/West/Renzie on deck for supplemental coverage.
- **OpCost-style machine-rate dataset plan**
   - [x] Define the schema for a default machine-rate table (`machine_name`, `role`, `ownership_cost_per_smh`, `operating_cost_per_smh`, `default_utilization`, `move_in_cost`, `source`, `notes`). Store it under `data/machine_rates.json` and expose loader helpers.
   - [ ] Transcribe core machine classes from Dodson et al. (2015) (feller-buncher, grapple skidder, processor, loader, road grader, etc.) and Hartley & Han (2007) (coastal grapple yarder, swing yarder, tower yarder) with FX/fuel adjustments to BC dollars (document CAD/USD rate and diesel price assumptions). 
   - [ ] Layer in FPInnovations repair/maintenance survey (Advantage Vol. 4 No. 23: "Repair and maintenance costs of timber harvesting equipment") as optional coefficients so operating costs can be recomputed from utilization hours when users supply custom labour/fuel inputs. (PDF now available—need to transcribe the per-machine regressions/percentages.)
   - [x] Implement a costing helper that blends the default rates with scenario overrides (e.g., `fhops.costing.machine_rates.load_defaults()` → `MachineRate` dataclass). Include utilisation scaling and move-in amortization logic per block/system.
   - [ ] Document the defaults (sources, currency conversions, typical utilisation) in the costing how-to and note how users can override rates via CLI/JSON config before the costing helper ships.
- Park the DRM-locked “Effects of Alternative Silvicultural Systems…” PDF until bandwidth frees up; partial-cut modeling will rely on TR119/TR125/Renzie (2006) and other accessible sources in the interim.

## Machine-Role Productivity Rollout (Steps 1–6)
1. [x] **Brushwood harwarder / forwarder variant**
   - Implemented via `fhops.productivity.laitila2020` using Laitila & Väätäinen (2020) Eq. 1–7; reproduces 6.5–8.4 m³/PMH range and exposes payload/grapple controls for registry + costing integration.
2. [x] **Conventional forwarder variants (biomass, slash, CTL)**
   - Added Ghaffariyan et al. (2019) ALPACA thinning models (14 t + 20 t forwarders) and Kellogg & Bettinger (1994) multi-product CTL regression so the registry/CLI can cover both plantation thinning and Pacific Northwest partial-cut scenarios; remaining action is to fold in FPDat slash-forwarder coefficients once available.
3. [ ] **Grapple skidder + shovel logger suites**
   - Pull regressions from Han & George, Kellogg & Bettinger (1994), McNeel & Rutherford, and FPInnovations grapple studies; normalise predictors (slope, turn length, turn volume) to FHOPS schema.
4. [ ] **Processors, loaders, merchandisers**
   - Use Berry (2019) + related theses to derive roadside processor/log-loader cycle models; ensure block attributes (species mix, product breakdown) drive productivity estimates.
5. [ ] **Cable, tethered, and aerial systems**
   - Mine Ünver-Okan (2020), Lee et al. (2018), and helicopter yarding reports for skyline/helilogging productivity; specify when tethered harvesters fall back to cable defaults.
6. [ ] **Manual / hybrid operations**
   - Capture provisional envelopes for motor-manual cutting, small forwarders, and hybrid crews; identify literature gaps so grad students can queue targeted field data collection.
