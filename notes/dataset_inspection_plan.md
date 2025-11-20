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
+ [x] Normalized Appendix 5 stand/operator metadata via `scripts/normalize_appendix5.py`, producing `notes/reference/arnvik_tables/appendix5_stands_normalized.json` with species mix, stand age, stem volume, ground condition/roughness, slope, and operator counts for skyline/tethered modelling inputs. Next step: plug this JSON into the skyline helper registry/costing defaults so slopes/ground descriptors feed the new Ünver-Okan + Lee models automatically.
- [x] Added Appendix 5 integration to the CLI/productivity helpers: `fhops.dataset appendix5-stands` surfaces the profiles, `estimate-cable-skidding` reuses the Ünver-Okan regressions with optional `--profile` lookups, and `fhops.reference.arnvik_appendix5` exposes the data for other modules.
- Implemented the Stoilov et al. (2021) skidder-harvester equations (delay-free and with-delays) as FHOPS helpers so `skidder_harvester` now has a baseline productivity model.
- Implemented the Laitila & Väätäinen (2020) brushwood harwarder equations (Eq. 1–7) as `fhops.productivity.laitila2020.estimate_brushwood_harwarder_productivity`; unit tests (`tests/test_laitila2020.py`) recreate the published 6.5–8.4 m³/PMH curves across forwarding distances.
- Added the Ghaffariyan et al. (2019) thinning forwarder models (small 14 t and large 20 t variants) as `fhops.productivity.ghaffariyan2019`, with regression tests matching Table 4 productivity values and optional slope multipliers for >10% trails.
- Captured the Kellogg & Bettinger (1994) CTL multi-product forwarder regression (`fhops.productivity.kellogg_bettinger1994`) so mixed/saw/pulp scenarios with explicit travel components can be estimated; tests mirror Table 8 productivity numbers.
- Added Sessions & Boston (2006) shovel-logging helper (`fhops.productivity.sessions2006`) so we can inspect road-spacing trade-offs (productivity, cost/tonne, profit). Regression tests replicate the published 4-pass scenario.
- Added Spinelli et al. (2017) excavator-based grapple yarder regression (`fhops.productivity.spinelli2017`) as an interim surrogate for the requested grapple-skidder model; still need Han & George field equations once available.
- Added Visser et al. (2025) mechanical feeding study (CroJFE) to quantify shovel-assist productivity (25–100 m³/h), utilization (61%), and time-use splits for excavator feeders on NZ steep ground – informs combined shovel/yarder modeling, plus extracted cycle stats (loading 36–107 s, feeding 15–26 s, waiting 15–74 s) showing waiting ≈40% of feeding time and the dominant effect of mean piece size (0.5–3.5 m³).
- Added Lee et al. (2018) small-scale cable yarder helper (HAM300 uphill/downhill regressions) in `fhops.productivity.cable_logging`; defaults use the published payloads (0.57/0.61 m³) and expose yarding/lateral distance + large-end diameter knobs so skyline/tethered costing can bootstrap until TR112/TR127 coefficients are recovered.
- Appendix 5 stand metadata normalized into `appendix5_stands_normalized.json` (111 entries across the Arnvik PDF) capturing species, stand age, stem volume, ground condition/roughness (Erasmus classes 1–5), slopes, and operator counts; these descriptors will drive the skyline/tethered helper defaults once tied into the registry.
- Logged McNeel (2000) longline yarding regression (Journal of Forest Engineering) covering coastal BC systems plus piece-size/line-length effects; key source for grapple yarder helper calibration (elemental regressions like Outhaul = 0.365 + 0.001576·Dist, Choke = 3.005 + 0.0805·LatDist, Unhook = 0.572 + 0.109·Pieces, and total-cycle `TC = 10.167 + 0.00490·Dist + 0.01836·Vdist – 0.01108·(Z1·Vdist) + 0.0805·LatDist + 0.1095·Pieces – 1.18·Z1`).
- Captured West, Sessions & Strimbu (2022) winch-assist + swing yarder steep slope system model (Forests 13:305) for integrated cut-to-length/long-log comparisons up to 115 cm DBH on 30–60% slopes, including their unified stemwise (Eq. 1) and roundtrip (Eq. 2) formulations (per-stem move time + quadratic volume terms; segmented loaded/unloaded travel speeds with slope/traction limits).
- Added Conor Bell (2017) OpCost thesis (Univ. of Idaho) describing the development/validation of USFS OpCost machine-rate model—primary reference for upcoming costing helper inputs (Miyata-style depreciation/utilization/wage components + business overhead and contractor-survey validation).
- Extracted OpCost input schema (Table 2.4) + cost workflow: 35 stand-level descriptors feed per-machine time models, then PMH → $/acre through machine rates built from fixed + variable owning/operating costs (Matthews 1942) with default PNW rates from Dodson et al. (2015); future costing helper will need a similar machine-rate table plus utilization/move-in handling. Dodson et al. provide per-machine assumptions (life 5 yrs, salvage 15–30%, utilization 60–90%, repair 75–100%, 6.5% interest, fuel $3.50/gal ≈ USD 0.92/L) and hourly rates (USD) averaged across Montana dealers—for BC work we’ll convert at ~1.33 CAD/USD (Bank of Canada 2024 avg) and bump diesel to ~CAD 1.80/L (~USD 1.35/L) to reflect higher Canadian fuel prices. Example conversions: feller-buncher ≈$149→$198 CAD/SMH (≈$249→$331 CAD/PMH); skidder $121→$161 CAD/SMH ($152→$202 CAD/PMH); processor $150→$200 CAD/SMH ($166→$221 CAD/PMH); stroke delimber $160→$213 CAD/SMH ($177→$235 CAD/PMH); loader $105→$140 CAD/SMH ($162→$215 CAD/PMH). FPInnovations Advantage Vol. 4 No. 23 repair/maintenance survey is benchmarked in 2002 CAD; Statistics Canada Machinery & Equipment CPI (Table 18-10-0005-01) gives a 2002→2024 cumulative factor of ≈1.56, so all FPInnovations R&M dollars now use that multiplier when we populate `data/machine_rates.json`.
- FPInnovations usage-class multipliers (Table 2, 5k–25k SMH buckets) are now stored with each default role so `fhops.costing.machine_rates.compose_rental_rate()` and `fhops dataset estimate-cost --usage-hours <n>` can scale the repair allowance for younger vs. end-of-life machines without hand-editing the rate table. Scenario authors can now set `machines.csv.repair_usage_hours` (nearest 5k bucket) so the default rental-rate backfill matches their assumed machine age, and the CLI can pick that up automatically via `--dataset ... --machine ...`.
- `fhops dataset inspect-machine` now shows the default owning/operating/repair breakdown (respecting `repair_usage_hours`) and `--json-out` writes the same data to disk, so dataset reviewers and automation can verify the implied rental rates without running `estimate-cost` separately.
- Telemetry (solver + `eval-playback`) now persists `machine_costs` snapshots (same JSON as `inspect-machine --json-out`) so KPI reports and tuning dashboards can trace which FPInnovations buckets were assumed for each machine run, and `fhops telemetry report` / `scripts/analyze_tuner_reports.py` surface the new `machine_costs_summary` column for downstream aggregation.
- Telemetry analytics now include a machine-cost trend chart and repair-usage alert table; CLI KPI summaries print a warning when `repair_usage_hours` ≠ 10 000 h, telemetry reports include the new `repair_usage_alert` column, and the CLI warns when deviations are detected.

### Newly Queued Tasks
- [x] Use `_machine_cost_snapshot` in any CLI solver JSON exports (outside telemetry) so ad-hoc consumers capture owning/operating/repair context without additional commands.
- [x] Extend the telemetry analytics notebooks/dashboards with pivots or charts grouped by `machine_costs_summary` (role × usage bucket) to visualize assumption drift across runs.
- [x] Add KPI/alert hooks that flag non-default FPInnovations buckets (e.g., highlight when `repair_usage_hours != 10 000` in KPI summaries or dashboard badges).
- Archived Chad Renzie (2006) UNBC thesis comparing partial cut vs clearcut productivity/cost in cedar-hemlock stands (east-central BC); provides partial-cut machine-rate data for future scenario defaults (ground-based clearcuts $10.95–15.96/m³, group selection $16.09–16.93/m³, group retention $13.39/m³, cable clearcut $15.70/m³; mechanized felling increased residual damage while grapple skidding reduced skidding wounds vs line skidding).
  - Added actionable notes from Renzie (2006): feller-buncher delay-free cycle regression `TPT = 1.391 + 0.006·Slope − 0.785·M0 − 0.110·M1` (P<0.05, SE 0.542) and grapple-skidder regression `TPT = 0.278 + 0.017·Distance + 0.316·Logs + 0.108·MaxLength + 0.027·Slope − 0.647·GroupSelection − 0.086·GroupRetention` (R²≈0.63, SE 2.60) plus walkthrough of Table 27–33 cost breakdowns (mechanized felling ≈$3.2/m³, grapple skidding inputs). Leave this study in the queue for future partial-cut helper work (needs JSON staging + CLI wiring).
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
| single_grip_harvester | [x] 260 models (CTL harvester variants) | Appendix 8 (pages 101–115) already ingested. |
| feller-buncher (swing-boom + DTT) | [x] 94 SB models + 5 DTT variants | Appendix 8 (FT FB rows). |
| feller-buncher_sim | [x] 14 | Simulation models – treat as optional. |
| harwarder | [x] 8 | CTL harwarder entries captured; need BC calibration later. |
| skidder_harvester | [x] 5 | Appendix 8 CTL skidder-harvester; check if applicable to BC ground-based systems. |
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

- [x] **Whole-tree forwarders / clambunks (Eriksson & Lindroos 2014; Laitila & Väätäinen 2014, 2020)**
  - [x] Digitise the Scandinavian long-distance forwarder/clambunk regressions (payload vs. distance, slope multipliers) and convert them into helper functions distinct from the CTL stack. (New `ForwarderBCModel` entries now wrap Eriksson & Lindroos final-felling/thinning payload models plus the Laitila & Väätäinen 2020 harwarder helper.)
  - [x] Add CLI flags mirroring the published predictors (payload, distance components, terrain class) and regression tests reproducing the tables/curves. (`fhops dataset estimate-productivity --machine-role forwarder` now accepts mean extraction distance, mean stem size, load capacity, and brushwood harwarder inputs; tests cover CLI + helper outputs.)
  - [x] Document applicability (final felling vs. salvage vs. plantation clean-up) and call out where BC calibration is still pending. (`docs/reference/harvest_systems.rst` now spells out when to pick each helper and flags missing BC slope factors.)
- [x] **Grapple skidders & shovel loggers / hoe-chuckers (Han et al. 2018; George et al. 2022; FPInnovations skidder & shovel-logging series)**
  - [x] Extract grapple-skidder and shovel-logger cycle-time equations (travel out/in, load size, slope class) and wrap them in `fhops.productivity.skidder_ft`. (Han et al. 2018 lop-and-scatter + whole-tree models now live in `estimate_grapple_skidder_productivity_han2018`.)
  - [x] Wire helpers into CLI + solver job defaults (`grapple_skidder`, `shovel_logger`) and add regression tests per reference. (`fhops dataset estimate-productivity --machine-role grapple_skidder` exposes the new flags; unit + CLI coverage asserts the outputs.)
  - [x] Capture scenario multipliers for trail spacing / decking strategy (from TN285/FPInnovations skidder reports) so costing workflows can reason about narrow vs. wide trail networks. (`--skidder-trail-pattern` and `--skidder-decking-condition` mirror TN285 ghost-trail layouts and ADV4N21 decking prep impacts; helpers/tests/docs now cover the stacked multipliers.)
  - [x] Implement a dedicated primary-transport hoe-chucker (shovel logger) productivity helper so excavator-based forwarding from stump to roadway landings is modeled explicitly (Sessions & Boston 2006 serpentine model now lives in `estimate_shovel_logger_productivity_sessions2006`).
  - [x] Wire the hoe-chucker helper into the CLI + harvest-system templates (`shovel_logger` jobs) so full-tree hoe-chucking scenarios no longer piggyback on the grapple-skidder surrogate. (`fhops dataset estimate-productivity --machine-role shovel_logger` exposes the new inputs; harvest-system overrides can inject swing counts later.)
  - [x] Push harvest-system overrides for shovel loggers (ghost-trail spacing, return-to-road frequency, swing counts) so scenario templates auto-populate hoe-chucker defaults similar to the grapple-skidder path. (`SystemJob.productivity_overrides` now seeds `ground_fb_shovel` / `ground_hand_shovel` with Sessions-style parameters and the CLI auto-applies them.)
  - [x] Mine FPInnovations shovel logging studies (e.g., TN261 loader-forwarding trial) for slope/bunching multipliers and integrate them as optional overrides (CLI now exposes `--shovel-slope-class`, `--shovel-bunching`, plus harvest-system overrides carrying those defaults).
  - [x] Wire harvest-system templates/datasets into the CLI so grapple skidders automatically pull the configured trail/deck defaults (`SystemJob.productivity_overrides`, `--harvest-system-id`, and `--dataset/--block-id` all fan out through `system_productivity_overrides`).
  - [x] Integrate GNSS-derived skidder speeds (Zurita & Borz 2025) so the Han et al. (2018) helper/CLI can switch between legacy regression speeds and cable-skidder/farm-tractor medians (`--skidder-speed-profile`, harvest-system overrides, docs/tests/changelog updated).
- [ ] **Skyline yarders / helicopter longline (Aubuchon 1982; Böhm & Kanzian 2023; Arnvik helicopter refs)**
  - [x] Add a running-skyline helper + CLI path (McNeel 2000 Madill 046 longline) so analysts can input horizontal span, deflection, lateral distance, pieces/turn, and pick Yarder A/B variants; include regression/unit tests + telemetry logging.
  - [ ] Extend the standing-skyline stack (TR125/TR127) with explicit deflection/intermediate-support predictors by digitising Aubuchon’s anchor-profile regressions (Appendix 8 in Arnvik 2024 only covers harvesters/feller-bunchers/harwarders; Appendix 9 = variable definitions, Appendix 10 = function parameters—no skyline/helicopter content). Supplement with the tower-yard datasets in `notes/reference/administrator,+jfe4_2tp02.pdf` (Howard & Coultish 1992) and the shovel-fed yarder timing in `notes/reference/04 Visser.pdf`.
    - [x] Port the Hensel et al. (1979) Wyssen standing-skyline regression (Appendix A eq. 15) into `fhops.productivity.cable_logging.estimate_standing_skyline_productivity_aubuchon1979` and surface it in the CLI as `aubuchon-standing` with log/crew inputs.
    - [x] Surface TR-125 single-span vs. multi-span (intermediate-support) cycle times in the helper/CLI so planners can see how skyline supports impact delay-free minutes and resulting productivity.
    - [x] Capture TR127 block metadata (Block 1/3 `latd2`, Block 5/6 `logs`, etc.) in docs + CLI guidance so analysts know when `--lateral-distance-2-m` or `--num-logs` is required.
    - [x] Extract Aubuchon standing-skyline anchor/deflection regressions (beyond Eq. 15) for the remaining tower-yard datasets and wire into CLI/docs.
      - [x] Kramer (1978) standing skyline: digitised the carriage-height + chord-slope equation from Appendix A Table I, exposed it as `aubuchon-kramer` with new CLI flags (`--carriage-height-m`, `--chordslope-percent`), and documented the allowable range (Skagit/Koller multi-span trials, 50–150 ft lateral, −30 % to +20 % chord slope).
      - [x] Kellogg (1976) tower yarder: added the lead-angle/choker-count regression as `aubuchon-kellogg`, converting payloads to cubic feet internally and adding `--lead-angle-deg` + `--chokers` CLI knobs so analysts can capture fan-out and rigging penalties. Tests/docs/telemetry updated to log the new predictors.
  - [x] Add helicopter longline regression(s) (payload vs. cycle time vs. flight distance) for `helicopter_longline` jobs. (Use Aubuchon 1982 rotorcraft cycle equations, Böhm & Kanzian 2023’s review pointers, plus the helicopter-cost references cited in Arnvik’s Appendix 1.)
    - `fhops.dataset estimate-productivity --machine-role helicopter_longline` now wraps the FPInnovations case studies (ADV6N25 Lama/K-Max, ADV5N38 Bell 214B, ADV5N13 Aircrane) with presets for light/medium/heavy lift. Analysts can override payload, load factor, weight→volume, and add delay minutes to reflect local mobilization or weather holds. `notes/reference_log.md` lists the supporting ADV/TR sources plus TR2015N52 drone-assisted strawline context.
  - [ ] Update docs/CLI so users can select skyline/helicopter models with clear input requirements and warnings about non-BC provenance; add harvest-system overrides for standing vs. running skyline corridors.
    - [x] Expand `docs/reference/harvest_systems.rst` + CLI help text so every skyline/helicopter model lists: predictors, calibrated range, provenance (BC vs. WA/ID vs. Korea), and caution flags. Mirror this in the CLI `--help`.
    - [x] Add `--harvest-system-id/--dataset/--block-id` plumbing to the skyline CLI (matching the productivity command) so corridor defaults/overrides can flow automatically.
    - [x] Define skyline/helicopter productivity overrides in `default_system_registry()` (e.g., `cable_standing`, `cable_running`, `helicopter`) with model selection + representative inputs (logs/turn, carriage height, deflection, load factor). Surface via CLI + telemetry when applied.
    - [x] Extend `tests/test_cli_dataset_skyline.py` (and harvest-system override tests) to cover the new system/default pathways and ensure warnings propagate.
  - ### Skyline action plan (refresh)
    - [x] Confirmed TR112’s public PDF only contains descriptive productivity/cost tables—no regression coefficients or appendices to mine. Do **not** spend further time re-scanning this report for “missing” regressions; focus recovery efforts on alternate FPInnovations/PNW sources. Regression functions from TR127 have already been extracted an integrated into FHOPS.
    - [x] **Add BC skyline presets** – Added TN147 (Madill 009 highlead), TN157 (Cypress 7280 swing yarder), and TR122 (Washington SLH 78 running skyline) presets to `fhops.productivity.grapple_bc` + CLI (`--grapple-yarder-model tn147|tn157|tr122-*` with case selectors). Docs/tests now describe when to select each preset and the CLI prints the observed BC cost/productivity values alongside CPI-adjusted costs.
    - [ ] **Skyline costing defaults** – Build CPI-aware machine-rate entries for representative skyline yarders (Madill 009, Cypress 7280C, Skylead C40) plus rigging/crew assumptions, and thread them into `inspect-machine` / `--show-costs` / harvest-system overrides.
      - [x] Transcribed TN157 (Cypress 7280B swing yarder + mobile backspar case studies) into `data/reference/fpinnovations/tn157_cypress7280b.json`, capturing cycle breakdowns, utilization, and the published $/piece + $/m³ costs so the Cypress preset isn’t blocked on TR112.
      - [x] Extracted TN157 trail-spar move-in/move-out timing (yarder vs backspar occurrences/ranges) and grapple payload assumptions; dataset fields now hold the per-case timing + payload stats the grapple-yard helper/harvest-system overrides will consume when we wire the presets.
      - [x] Transcribed TN147 highlead case studies into `data/reference/fpinnovations/tn147_highlead.json` (seven Madill 009 trials with timing, payload, and $/m³ outputs) so we have a second coastal BC reference to pair with the Cypress swing yarder presets.
      - [x] Extracted the TR122 Washington SLH 78 running-skyline tables into `data/reference/fpinnovations/tr122_swingyarder.json`, capturing extended-rotation vs. shelterwood vs. clearcut productivity/cost breakdowns and the cycle-time distributions (Table 6) for partial-cut presets.
      - [ ] **FPInnovations skyline backlog (from reference log “Next Actions”)**
        - Cable Yarding (FNCY series) – References logged (`notes/reference_log.md:120` onward) for FNCY1/4/10/11/12/17. FNCY1 (Igland-Jones Mini-Alp on Timberjack 330) reviewed: downhill yarding ~85 m³/shift with three-person yarding crew + shared skidder/bucker, uphill ~113 m³/shift using a Koller carriage. No regression tables but provides payload/crew/layout notes for micro-yarders. FNCY4 (radio-controlled chokers on a Washington 118 swing yarder) reviewed: reports 280–340 m³/day uphill grapple yarding with a four-person crew, landing release time cut to 20 s, and battery/service lessons—useful for skyline efficiency assumptions. FNCY10 (Eastern Canada equipment review) logged: specs/crew sizes for small skyline/highlead yarders (Christie, EcoLogger, Smith Timbermaster, Télétransporteur); planning reference only. FNCY11 (road/landing/backspur occupancy survey) logged: skyline haul-road density ≈19 m/ha vs. 52 m/ha for grapple systems—handy for footprint modelling. FNCY12 (intermediate supports with Thunderbird TMY45) logged: productivity ramp 102→189 m³/shift (avg 166 m³), rigging diagrams, and man-day comparisons vs. Skylead C40—useful for long-span skyline costing. FNCY17 (Telecarrier TL-3000C cedar salvage) logged: 2-person remote-carriage skyline with 6 m×0.8 m cedar logs, 500 m reach ceiling, 35 L/day fuel; helpful when modelling light skyline/salvage setups. FNCY list now fully triaged.
        - Advantage skyline issues – ADV1N5, ADV5N28, ADV7N3, etc. already catalogued with short abstracts (`notes/reference_log.md:13,39,45`). ADV5N28 is fully wired, ADV7N3 now powers `--processor-model adv7n3` (and the skyline harvest-system presets auto-select the deck costs), ADV1N35 ships as `--grapple-yarder-model adv1n35`, ADV1N40 just landed as the `adv1n40` Madill 071 downhill preset, ADV6N7 now backs both the `adv6n7` grapple-skidder helper and the `ground_fb_*` harvest systems (auto-selecting the Caterpillar 535B defaults + loader-support ratio), and ADV2N21’s partial/patch cost matrix lives in `data/reference/fpinnovations/adv2n21_partial_cut.json` (`fhops dataset adv2n21-summary`). ADV1N5 is now mined for salvage guidelines (debarking upgrades, charcoal-dust controls, log sorts, grapple yarding of sensitive slopes, portable milling/in-woods chipping); docs/CLI planning sections reference those cautions even though no regression exists and the new `ground_salvage_grapple` / `cable_salvage_grapple` harvest systems bundle the defaults. Next Advantage-specific work: surface ADV1N5’s portable mill/in-woods chipping toggles in the scenario generator so salvage scheduling knobs live beside the presets. 
        - November 2025 drop batching – Still pending. Plan is to skim ADV1N12–ADV9N1 (Advantage wave), FNPC17/19/21/28 + FNSF8/9/11/34 (Field Notes), and TN123–TN296 + TR94/109/2017N34/2017N57/2021N93/2023N17 (Technical Notes/Reports) for skyline/forwarder datasets, then summarize findings in `notes/reference_log.md` and mirror actionable items here.
        - Inventory hygiene – duplicate PDFs not reviewed; plan is to dedupe the `notes/reference/` tree after each batch and mirror actionable findings here so skyline helper priorities stay synced with the bibliographic queue.
    - [ ] **Scenario wiring + synthetic coverage** – Teach harvest-system templates and the synthetic generator to auto-populate skyline predictors (span, deflection, lateral distance, payload, latd2) and ensure telemetry/regression tests cover those defaults.
  - ### Helicopter action plan (refresh)
    - [ ] **Consolidate FPInnovations heli datasets** – Transcribe ADV3/4/5/6 + TR2015N52 cycle/cost tables into a structured JSON (`data/productivity/helicopter_fpinnovations.json`) capturing payload, hook/wait delays, fuel, and CPI metadata for Lama, K-Max, Bell 214B, and S-64E presets.
    - [ ] **Cost integration** – Create machine-rate roles for each helicopter class (including mobilisation ferry/crew costs) and have `--machine-role helicopter_longline` + `--show-costs` report owning/operating splits alongside productivity.
    - [ ] **Telemetry & docs** – Expand docs/CLI to show when FPInnovations vs. Aubuchon equations are used, cite the specific ADV/TR source, and log load-factor/payload overrides in telemetry so downstream costing can audit heli assumptions.
- [x] **Roadside processors / loaders / hoe chuckers (Labelle et al. 2016/2018)** — Complete.
    - [x] Landing-processor and loader datasets ingested across FPInnovations (ADV5N6, TN-166, TN-103, TR-87, TR-106, TN-46), Berry/Labelle, HYPRO 775, Borz, Bertone, Spinelli, Nakagawa, and Visser, with CPI metadata and CLI/docs/tests for every preset.
    - [x] Reference triage finished: Kellogg (JFE 5(2)) feeds the `kellogg1994` harvester helper; UNBC hoe-chucking remains a documentation reference exposed via `fhops dataset unbc-hoe-chucking`; no additional landing preset required.
    - [x] Peer-reviewed integrations (HYPRO, Borz, Bertone, Spinelli, Nakagawa, Visser) plus carrier profiles and automatic bucking multiplier are live in CLI/docs/tests.
    - [x] Loader helper interface consolidated around TN-261, ADV5N1, ADV2N26, Barko 450, and Kizha 2020, with CPI-aware machine rates, harvest-system overrides, and soil-disturbance notes. (FPDat loader traces remain deferred until FPInnovations data access is granted.)
    - [x] Cost normalisation, telemetry hooks, and documentation (coverage tables in `docs/reference/harvest_systems.rst`) completed; no outstanding work items remain for this theme.
            - [x] Leverage Borz et al. (2023) landing-harvester dataset (“Bucking at Landing by a Single-Grip Harvester”) as a dedicated preset.
                - `data/productivity/processor_borz2023.json` holds the observed averages (efficiency 0.047 PMH/m³, productivity 21.41 m³/PMH, fuel 21 L/h ≈0.78 L/m³, cost 10–11 €/m³, recovery 95 %).
                - `estimate_processor_productivity_borz2023` and `--processor-model borz2023` expose the preset (no special inputs beyond optional tree volume), providing a purpose-built landing benchmark within the CLI/docs/tests.
            - [x] Transcribe Nakagawa et al. (2010) (Hokkaido excavator processor) cycle regressions to give us a shovel-processor helper keyed to DBH.
                - `data/productivity/processor_nakagawa2010.json` now stores both published regressions (0.363·DBH^1.116 with DBH in cm and 20.46·V^0.482 with volume in m³) plus the study notes (Timberjack 746B + Komatsu PC138US carrier, 0.25 m³ stems, 10.8 m³/PMH observed).
                - `estimate_processor_productivity_nakagawa2010` chooses the DBH or piece-volume equation based on the supplied predictor and applies an optional delay multiplier so the helper can represent delay-free PMH₀ or fold in landing waits.
                - `--processor-model nakagawa2010` (with `--processor-dbh-cm` and/or `--processor-piece-size-m3`) now renders the preset in `fhops.dataset estimate-productivity`, docs explain the new options, and helper/CLI tests exercise both regression paths. Next up: pivot to the remaining landing-processor backlog (Spinelli log-sort follow-ups already live; Spinelli 2010 helper completed earlier).
        - [x] Capture the Labelle & Huß (2018) automatic bucking vs. quality bucking deltas (≈+6 m³/PMH, +3–5 €/m³) into `data/reference/processor_labelle_huss2018.json` so the processor CLI can expose an optional `--automatic-bucking` multiplier.
            1. [x] **Prioritisation pass** – chose the Labelle & Huß multiplier as the next increment (TN-46 loader costing + FPDat placeholders stay queued) and locked scope to “multiplier toggle + telemetry/docs”.
            2. [x] **Data extraction** – `data/reference/processor_labelle_huss2018.json` now stores the published PMH₀ and €/m³ values for manual vs. automatic treatments (Table 8/10) plus base-year metadata so the helper can consume the 12.4 % productivity uplift or €3.3/m³ revenue bump directly.
            3. [x] **Dataset + helper updates** – helpers now accept an optional `automatic_bucking_multiplier` parameter, load the Labelle & Huß dataset, and apply the +12.4 % delay-free uplift when requested.
            4. [x] **CLI/docs/tests** – added `--processor-automatic-bucking`, documented the behaviour (docs + changelog), and extended the CLI/unit tests to assert that the multiplier path changes the reported productivity and prints the Silva Fennica citation/revenue note.
        - [x] Capture Berry tree-form penalty factors directly from the regression output (category 1 = +56 % time, category 2 = +84 % time) and expose them as configurable multipliers instead of hard-coded constants in `processor_loader.py`. Helper now reads the multipliers/utilisation from `data/productivity/processor_berry2019.json`.
    - ### Roadmap To Wrap Landing Processor/Loader Theme (BC coverage closure)
        - Mission: lock down documentation/tests so ADV5N6/TN-166/TR87/TR106/Berry/Labelle/HYPRO/Borz/Bertone/Spinelli/Nakagawa + Barko/ADV2N26/ADV5N1/TN-261 loader presets cover the BC case-study palette without dangling “maybe someday” tasks.
        - [x] Document coverage matrix:
            - Added two cheat-sheet tables to `docs/reference/harvest_systems.rst` (“Landing processor presets” and “Loader / hoe-forwarder presets”) listing region, carrier/head, utilisation defaults, and notes for every preset so BC analysts can pick models quickly.
        - [x] Decide UNBC hoe-chucking landing reference path:
            - Re-read the Renzie (2006) appendix/tables: only manual hoe-chucking cost summaries (Tables 20–21 and Table 33) exist—no cycle-time breakdowns or mechanised landing processor timings beyond SMH-based cost per m³.
            - Outcome: keep `data/reference/unbc_hoe_chucking.json`/`unbc_processing_costs.json` as documentation references (already exposed via `fhops dataset unbc-hoe-chucking`), but do **not** build a processor helper. Future interior hoe-chucking presets will require new data; this task is now closed.
        - [x] Resolve open backlog items explicitly:
            - Berry skid-size task closed (CLI already auto-adjusts utilisation; docs updated).
            - NZ landing preset formally deferred (no additional data beyond Visser & Tolan; Kellogg data used for harvester helper).
        - [x] QA + release prep:
            - Focused pytest matrix complete: `pytest tests/test_productivity_helper.py tests/test_cli_dataset_processor.py tests/test_cli_dataset_loader.py` (all green).
            - Remaining admin: roll the final summary into the next changelog entry/status update once we cut the wrap-up commit.
    - [x] Extract the skid-size vs. delay relationship from Berry Section 5.5 and evaluate whether it warrants an optional `skid_size_m3` input (or just document it as a utilisation warning).
        - Status: Already implemented via `--processor-skid-area-m2` (Berry helper auto-adjusts utilisation when the user supplies a landing area). Updated `docs/reference/harvest_systems.rst` with guidance so the CLI behaviour is discoverable.
    - [x] Mine `administrator,+jfe5_2tp04.pdf` for the NZ landing-processor equations (stems/hr vs. DBH/log sorts) and queue them as additional helper variants (likely `processor_model nz_landing_2004`).
        - Outcome: the administrator/Kellogg report provides CTL harvester/forwarder regressions but no standalone landing-processor timing beyond the Visser & Tolan log-sort study (already implemented as `visser2015`). We therefore reused the data for the `kellogg1994` harvester helper and will not add a duplicate landing preset.
        - [x] Captured the published harvester (vol/PMH vs. DBH) and forwarder regressions plus cost assumptions from Kellogg & Bettinger (1994) into `data/reference/administrator_jfe5_2tp04.json` so we can reference them when designing CTL thinning presets.
        - [x] Added a `kellogg1994` CTL harvester helper/CLI option (`--ctl-dbh-cm`) so analysts can pair the Timberjack 2518 regression with the existing Kellogg forwarder models for PNW-style thinning scenarios.
    - [x] Pull the UNBC hoe-chucking processor timing data (`notes/reference/unbc_15814.pdf`) and decide if it fits as another helper or as documentation for steep/interior utilisation multipliers.
        - Decision: thesis provides cost per treatment (group selection/clearcut) and SMH-based $/m³ only; no mechanised processor regression to encode. Leave as reference command (`fhops dataset unbc-hoe-chucking`) and revisit only if new FPInnovations data emerges.
  - [x] Provide helper functions for `roadside_processor` and `loader`, exposing key predictors (piece size, log sort count, decking distance) and regression tests. Tie processor cost factors back to `notes/reference/Development_and_Validation_of_.pdf` (OpCost) and `notes/reference/harvestcost-woodstock.pdf` so CLI outputs match Woodstock/OpCost conventions.
    - [x] Processor helper interface now supports `--processor-model berry2019` (piece size, tree form, crew, utilisation), `--processor-model labelle2016` (acceptable vs. unacceptable tree-form classes), `--processor-model labelle2017` (poly/power DBH variants from the NB excavator-based trials), `--processor-model labelle2018` (rubber vs. tracked Ponsse regressions from Bavaria), and the Labelle 2019 DBH/volume hardwood presets. Docs/CLI explicitly warn that the Labelle regressions are PMH₀ outputs for hardwood-dominated blocks (rare in BC, handy for export scenarios).
    - [x] Added `--processor-model labelle2016` (sugar maple acceptable vs. unacceptable tree-form groups) via `estimate_processor_productivity_labelle2016(tree_form, dbh_cm, delay_multiplier)`, giving analysts a hardwood reference sourced from eastern Canada (Croat. J. For. Eng. 2016).
    - [ ] Loader helper interface sketch:
        - [x] Interim coverage: FERIC TN-261 loader-forwarder timing captured in `data/productivity/loader_tn261.json` and exposed via `estimate_loader_forwarder_productivity_tn261` (`--machine-role loader` with piece-size/distance/slope/bunching/delay knobs).
        - [x] Digitise ADV5N1 (loader-forwarding) productivity curves:
            - [x] **(Greg)** Provide a manually digitised set of forwarding-distance vs. cycle-time points for Figure 9 (slope class 0–10 %) so we can fit the baseline regression and stash it in `data/productivity/loader_adv5n1_points.json` (coefficients supplied 2025‑11‑20).
            - [x] Extract the forwarding time vs. distance curve (Figure 9) from `notes/reference/ADV5N1.PDF`—either via vector data or manual digitising—to recover the baseline linear equation (`CT = 1.00 + 0.0432·x`).
            - [x] Convert the slope-class adjustments (0–10% baseline, +18% time for 11–30%) into explicit multipliers (manual extraction gives ``CT = 1.10 + 0.0504·x`` for 11–30%).
            - [x] Reproduce the productivity/cost curves (Figures 10–11) using the extracted cycle-time equation, 2.77 m³ payload, and 93% utilisation so the helper can emit both m³/PMH and $/m³ (`--loader-model adv5n1` now mirrors the published curves).
        - [x] Encode ADV2N26 (Trans-Gesco TG 88 + John Deere 892D-LC loader-forwarder) so the clambunk/hoe-forwarding presets have a BC reference:
            - [x] Port Appendix III’s regression (`CT = 7.17 + 0.0682·DE + 0.396·ST`, with DE = 35–550 m, ST = 3–42 stems/cycle) and productivity formula (`60·CV·U / (CT + DT)` with CV≈29.9 m³/cycle, util. from Table 3, DT≈5% of cycle) into a helper stub (`estimate_clambunk_productivity_adv2n26`).
            - [x] Add loader-forwarder/landing loader defaults from Table 4 (41 m³/SMH at $2.88/m³ for the 892D-LC; 35 m³/SMH at $4.04/m³ for the Link-Belt LS-4300) so analysts can select a hoe-forwarding preset even while ADV5N1 digitization is in flight (`--loader-model adv2n26` plus new CLI knobs).
            - [x] Surface the soil-disturbance survey (20.4 % trail occupancy with class-specific widths and exposed-mineral-soil percentages) as planning defaults/CLI warnings for clambunk-assisted corridors (CLI now prints the trail-width/exposed-mineral-soil stats when `adv2n26` is selected and docs reference the same).
        - [ ] Catalogue additional loader references in the log (ADV2N62.PDF, ADV5N45.PDF, ADV15N2.PDF, FPDat loader traces):
            - [x] For each, pull loader timing details (predictors, sample sizes, slope/terrain) and record them in `notes/reference_log.md` (entries added for ADV2N62 loader-forwarding, ADV5N45 mechanized processors + loader support, and ADV15N2 steep-slope loader-forwarders).
            - [x] Identify which references include multi-predictor regressions (e.g., decking distance + sorts) to complement ADV5N1’s distance-only model (ADV15N2 documents slope/felling-direction multipliers; ADV2N62 provides trail occupancy/loader-processing cost splits for combo systems).
            - [ ] **(Greg)** FPDat loader traces remain out-of-reach unless FPInnovations explicitly shares a datapack with us. Do not schedule any extraction tasks until I confirm access (“rolling deep” with FPInnovations is not our situation). Leave this flagged for a future phase only if data becomes available.
        - [ ] Stage structured data:
            - [x] Build `data/productivity/loader_models.json` capturing coefficients, payload/utilisation defaults, and soil-disturbance metadata (TN-261, ADV2N26, ADV5N1 now covered).
            - [x] Add companion entries for richer models so the helper/CLI can switch between variants and print metadata-driven warnings.
        - [ ] Helper implementation:
            - [x] Add `estimate_loader_forwarder_productivity_adv5n1(...)` returning productivity/cost with slope adjustments (coefficients digitised manually by Greg on 2025‑11‑20).
            - [x] Extend `fhops.dataset estimate-productivity --machine-role loader` with `--loader-model adv5n1`, slope-class/payload knobs, and metadata-driven warnings while keeping TN-261/ADV2N26 as fallbacks.
            - [x] Update docs/tests/planning so the loader path mirrors the processor coverage once the new helper is live (docs now describe all three loader models + soil disturbance warnings; regression tests cover TN261/ADV2N26/ADV5N1).
            - [x] Wire harvest-system overrides into the loader helper so `ground_fb_skid` (TN-261), `ground_fb_shovel` (ADV5N1), and `steep_tethered` (ADV2N26) auto-populate the required inputs; CLI telemetry/logging now records when these presets apply.
  - [x] Document how these interact with forwarder/skidder productivity so scenario cost rollups stay consistent (e.g., ghost-trail settings from TN285, loader-forward hybrids from `notes/reference/pnw_rp430.pdf`). Added the “Coordinating with forwarder / skidder models” subsection to `docs/reference/harvest_systems.rst` so analysts mirror the TN-285 ghost-trail pattern, ADV2N26 payload splits, and ADV5N1 shovel-fed assumptions when chaining helpers.
  - [ ] Digitise the Berry/Labelle landing-processor datasets (`notes/reference/Berry, Nick_Final-Dissertation.pdf`, `administrator,+jfe5_2tp04.pdf`) into structured tables (CSV/JSON) with clear predictor definitions so helpers/tests can reuse the published coefficients).
    - [x] Berry 2019 piece-size/tree-form regression captured in `data/productivity/processor_berry2019.json` (equation + utilisation + tree-form multipliers).
    - [x] TN-261 loader-forwarding detailed timings captured in `data/productivity/loader_tn261.json` (piece size, distance, slope, productivity pairs).
    - [x] Labelle et al. productivity models staged via Arnvik (2024) Appendices 8–10 (see `data/productivity/processor_labelle_models.json`); DBH and volume (`V₆/V₆d`) variants now power the hardwood helper. Next step: expose the earlier Labelle (2016/2017/2018) regressions and map their predictor codes so analysts can pick the study that best matches their prescription.
  - [x] Wire the processor/loader helpers into `fhops.dataset estimate-productivity` with dedicated CLI flags/telemetry, and add docs/tests once the regressions land (done for Berry/Labelle DBH + TN-261 loader).
  - [ ] Filter Lahrsen FPDat data to tethered harvesters/shovels and derive interim regressions (stem size vs. slope vs. tether load). *(Blocked until FPDat exports are furnished—current collaboration level does not include raw FPDat access; wait for explicit go-ahead.)*
  - [ ] Cross-validate against published winch-assist case studies (e.g., FPInnovations BMP v2, Kellogg winch trials) and add CLI flags for anchor slope limits.
  - [ ] Note open items for payload/slope derating until more FPInnovations data arrives.
- [ ] **Manual operations (BC/Quebec hand-fall time studies)**
  - [ ] Gather historic hand-falling / bucking / processing time-motion studies and encode them as baseline productivity constants or simple regressions.
  - [ ] Add documentation/CLI warnings that manual paths are placeholders pending modern data, and flag recommended use cases (e.g., retention islands, wildlife trees).

- [ ] **Helicopter helper follow-ups**
  - [ ] Parse the Arnvik/Aubuchon helicopter appendices (payload vs. cycle time) and decide whether to add supplemental models or recalibrate load-factor defaults for the existing FPInnovations presets.
  - [ ] Extend the `helicopter_longline` CLI/docs with provenance/warning text similar to the skyline section, plus harvest-system overrides for multiple aircraft (Bell 214B vs. S-64E vs. K-Max) once additional regressions are digitised.

- [ ] **Grapple yarder system overrides**
  - [x] Add `_apply_grapple_yarder_system_defaults` to the productivity CLI so harvest-system presets can populate grapple-yarder predictors when users only specify `--harvest-system-id`.
  - [x] Expand `default_system_registry()` overrides for `cable_running` (and any other grapple corridors) with grapple-specific defaults (payload, travel distances, deflection) in addition to the skyline model swap.
  - [x] Add regression/CLI tests proving the grapple-yarder overrides fire and document the behaviour in `docs/reference/harvest_systems.rst`.
- [ ] **Appendix 4/5/7 normalization follow-ups**
  - [ ] Parse the new raw CSVs into structured schemas: machine specs per publication/model (Appendix 4), stand/operator metadata (Appendix 5), and DV abbreviations (Appendix 7).
  - [ ] Attach these metadata blobs to each registry entry so CLI output can show machine defaults, stand context, and human-readable predictor descriptions (PV/PW/TV/TW/TU/etc.).
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

## Productivity Backlog Plan

### FT System Primary Transport (stump to roadside)

- various types of skidders
- hoe chuckers
- any "modifier" models to capture terrain or bunch size or piece size or species or prescription (e.g., commerical thinning intensity versus clearcuts) or whatever 

### CTL System Harvester productivity

Candidate references already in the repository; convert each into a helper/plan:

- [x] `notes/reference/fpinnovations/ADV6N10.PDF`
  - Publish the single-grip harvester regression (function of stem volume, number of products, stems/cycle, mean log length) beside the forwarder helper.
  - Add CLI switches paralleling ``adv6n10-shortwood`` so analysts can quantify harvester-side sorting penalties in boreal multi-product CTL.
  - Tests: numeric recreation of Appendix 1 values + CLI smoke.
- [x] `notes/reference/fpinnovations/ADV5N30.PDF`
  - Encode removal-level modifiers (30/50/70 %) and brushing deltas, wrapping Timberjack 1270 data into a helper or scenario multiplier.
  - Document when to apply (white spruce commercial thinning, Alberta) and how to blend with forwarder models.
  - Tests verifying per-removal productivity against the tables.
- [x] `notes/reference/fpinnovations/TN292.PDF`
  - Build a harvester productivity function parameterised by mean tree volume and stand density (based on Kenmatt/Brinkman study).
  - Surface optional cost outputs or elasticities for pipeline integration.
  - Regression tests spanning the min/max tree-size brackets.
- [x] `notes/reference/fpinnovations/TN285.PDF`
  - Translate the observed impacts of trail spacing, removal intensity, and pre-cleaning into scenario multipliers (or helper flags).
  - Add documentation emphasising when pre-cleaning is uneconomic.
- [x] `notes/reference/fpinnovations/ADV5N9.PDF` / `ADV2N21.PDF`
  - Capture BC/QC second-thinning harvester productivity under alternate trail networks and removal intensities.
  - Provide quick-look tables or multiplier hooks so CTL blocks with existing trail networks can be modelled without manual spreadsheet work.

#### CTL scenario multipliers (TN285 / ADV5N9 / ADV2N21)

- TN285 (NB/QC thinning) takeaways:
  - Pre-cleaning delivered a single 31 % harvester productivity bump in natural spruce but the labor cost (~$16.92/PH vs. observed $130/ha savings) rarely pencils out; treat chain-saw brushing as an optional scenario flag, not a default multiplier.
  - Trail spacing: harvester output is insensitive to ghost trails, but narrow extraction spacing (≤18 m) drives 20–40 % higher forwarder costs because loads shrink to 0.10 m³/metre vs. 0.20 m³/metre at 27–30 m spacing. When modelling dense ghost-trail networks, include a +25 % extraction-cost alert.
  - Removal intensity (30 % vs. 40 %) and two-pile product sorting showed no statistically significant productivity change inside the study noise; document that biological objectives should drive those choices.
- ADV5N9 (Abitibi second thinning): 30 % vs. 50 % removal and “reuse old trails vs. cut new trails” produced comparable harvester/forwarder productivity; use this reference to justify keeping Lahrsen/TN292 baseline unless site biology demands otherwise.
- ADV2N21 (Okanagan interior BC): productivity scales primarily with average tree size (80 % of variance explained) and site limitations (patch/partial vs. clearcut). Use Figure 6 slopes when back-calculating expected PMH for salvage/patch prescriptions, and flag cost ranges ($8.49/m³ clearcut base to $15.10/m³ patch cut) for interior planning scenarios.

### Forwarder / grapple-skidder coverage
- [x] Parse Arnvik Appendix 8–11 JSON dumps (`notes/reference/arnvik_tables/`) to isolate forwarder/harwarder/grapple-skidder regressions; capture predictor ranges + units in a machine-readable table under `data/productivity/arnvik_forwarder.json` (script: `scripts/build_arnvik_forwarder_table.py`, currently surfaces harwarder + skidder-harvester rows—the appendices do not include standalone forwarder codes, so the forwarder role is proxied via harwarder models until additional data surfaces).
- [x] Acknowledge the Arnvik gap explicitly: document in docs/planning that Appendix 8 only covers harvesters/feller-bunchers/harwarders (per thesis title) and will not produce primary-transport regressions; use the dataset solely for harwarder validation. (`docs/planning/productivity_gaps.rst`)
- [x] Pick BC-appropriate equations (terrain / stem size ranges similar to Lahrsen + FPInnovations studies). Document gaps where coefficients are Scandinavian-centric and note pending FPInnovations confirmations. (same planning note outlines AFORA/ALPACA + Kellogg stack and FPInnovations asks)
- [x] Implement helper module (`fhops.productivity.forwarder_bc`) with thin wrappers per model; wire into CLI (`fhops dataset estimate-productivity --machine-role forwarder`) and add pytest coverage comparing against published PMH/m³ tables.
- [ ] Update dataset defaults/synthetic generator (`src/fhops/scenario/synthetic/generator.py`) so forwarder productivity references the new helper; refresh fixtures or tests that assert production totals.
- Reference inventory for forwarder work:
  - `notes/reference/sb_202_2019_2.txt` — Ghaffariyan et al. (2019) AFORA/ALPACA models (Eq. 2–3) giving closed-form m³/PMH₀ curves for 14 t and 20 t forwarders as a function of extraction distance plus slope multipliers (10–20% → ×0.75, >20% → ×0.15). Best quick-win for coding because equations are already explicit.
  - `notes/reference/forests-13-00305-v2.txt` — West. Oregon tethered harvester-forwarder Monte Carlo (Allman et al. 2021) with Equation (1)/(2) for cycle time contributions and Appendix S1 payload-vs-slope/distance regressions (Pl,kg). Use these to derive slope penalties/payload caps for coastal BC steep-slope scenarios when we port the ALPACA functions.
  - `notes/reference/gagliardi.pdf` — Gagliardi et al. (2023) multi-product forwarder study (two Ponsse capacity classes) with regressions covering load size, extraction distance, product assortments, and fuel consumption. Use to validate the high-capacity end of `ForwarderBCModel` and to seed multi-assortment/fuel multipliers.
  - `notes/reference/forests-14-01782.pdf` — Munis et al. (2023) tactical forwarder planning with telemetry-driven routing heuristics; pull the distance/turn defaults into the synthetic generator so dataset templates don’t assume perfect trails.
  - `notes/reference/harvestcost-woodstock.pdf` — Paradis (2011) guidance for feeding productivity-based harvest costs into Woodstock; reference when exposing CLI forwarder summaries to Woodstock exports.
  - `notes/reference/sb_202_2019_2.txt` Table 4 + Figures 7/8 and `tests/test_ghaffariyan2019.py` already provide expected outputs; need to wrap them in CLI/regression harnesses and document the assumptions (Australia pine/euc thinning, gentle terrain) before grafting BC-specific adjustments.
  - [x] CLI now exposes `--slope-class` buckets (flat, 10–20 %, >20 %) wired to the ALPACA multipliers so analysts can pick the published factors without manual math; unit tests cover the new path.
  - `notes/reference/fpinnovations/ADV2N21.PDF` — Okanagan (BC) Timberjack 1270/1010 partial-cut program (1996–1999) with nine block types; provides normalized 150 m forwarding cycle times, $/m³ deltas vs. clearcut baseline, and soil-compaction data for multi-pass forwarder trails. Useful for calibrating distance-penalty and disturbance constraints but does not add a closed-form regression.
  - `notes/reference/fpinnovations/ADV2N39.PDF` — Lac Saint-Jean (QC) Timbco TF-820D harvester-forwarder combo (LogMax 750 + 15 m³ bunk) with 60 SMH harvesting / 40 SMH forwarding schedule. Captures 19 m³/PMH (harvest) and 25 m³/PMH (forward) at 175 m, changeover times, and optimal weekly production vs. extraction distance, informing utilization heuristics for single-machine hybrid systems.
  - `notes/reference/fpinnovations/ADV2N62.PDF` — Interior BC loader-forwarding program (three excavator-based loaders on 33–41 % slopes) documenting 265 m³/shift throughput, $15.20/m³ extraction + loading cost, and trail-density/soil-disturbance metrics; use for steep-slope loader-forwarder role assumptions.
  - `notes/reference/fpinnovations/ADV2N9.PDF` — Bowater (NB) shortwood forwarder productivity study (six products, 3.1 m and shorter logs) quantifying the impact of product counts, log length, slope, and pile size on cycle time via GPS-tagged piles; refreshes multi-product correction factors for shortwood roles.
  - `notes/reference/fpinnovations/ADV3N29.PDF` — Fuel-consumption survey for western Canadian ground-based systems; provides diesel-equivalent L/m³ and GHG figures for forwarder/skidder/loader workflows to pair with productivity estimates when deriving PMH→fuel/CO₂ outputs.
  - `notes/reference/fpinnovations/ADV5N30.PDF` — Alberta commercial-thinning trial (Timberjack 1270/1210B) with brushing crew assist; forwarder shift productivity 22–30 m³/PMH (30–70 % removal) and detailed timing up to 64 m³/PMH. Useful for calibrating removal-level multipliers once BC payloads are available.
  - `notes/reference/fpinnovations/ADV6N10.PDF` — Boreal CTL sorting study that publishes explicit harvester + forwarder productivity equations (forwarder depends on payload, travel speed, number of products per trail, mean log length, trail length). First FPInnovations regression we can port into `fhops.productivity.forwarder_bc` to cover shortwood multi-product scenarios.
  - `notes/reference/fpinnovations/ADV6N7.PDF` — Caterpillar 535B grapple skidder trial (northern Vancouver Island) paired with loader-forwarding; now digitised as `data/reference/fpinnovations/adv6n7_caterpillar535b.json` and exposed via `--grapple-skidder-model adv6n7` (decking-mode selector + loader-support costing) so we have a coastal BC skidder preset for skyline conversions.
  - [x] Ported the ADV6N10 forwarder regression into `fhops.productivity.forwarder_bc` (`adv6n10-shortwood`), exposed CLI options for payload/log length/trail metrics, and added regression tests so analysts can evaluate shortwood multi-product cases directly.
  - [x] Documented when to use each forwarder model (Ghaffariyan, Kellogg, ADV6N10) in `docs/reference/harvest_systems.rst` so CLI users can match blocks to the appropriate regression without digging through planning notes.

  Next steps to close this section (per 2025-11-18 review):
 1. [x] Document the Arnvik Appendix 8 gap in the planning docs so analysts understand it only covers harvesters/feller-bunchers/harwarders and should not be applied to primary transport.
 2. [x] Capture the BC-ready forwarder equation mix (Ghaffariyan 14 t/20 t + slope multipliers, Kellogg saw/pulp/mixed, pending FPInnovations payload confirmations) with explicit caveats about Scandinavian/Australian coefficients.
 3. [x] Add `fhops.productivity.forwarder_bc` as the canonical wrapper, wire it through `fhops dataset estimate-productivity --machine-role forwarder`, and extend pytest coverage to lock in the published PMH curves.
  4. Update the dataset defaults and synthetic generator so forwarder machines pull productivity from the new helper and refresh any fixtures that assert production totals.

  **FPInnovations November 2025 drop — review workflow**
  - Batch the 46 newly filed FPInnovations PDFs (Advantage, Field Note, Technical Note, Technical Report) under `notes/reference/fpinnovations/` into three scanning waves:
    1. Advantage issues (`ADV1N35` … `ADV9N1`) to mine for skyline/forwarder hybrids now that ADV1N12’s regressions are in code. Immediate targets: ADV2N21 (Okanagan partial-cut forwarder/skidder travel penalties) and ADV1N5 follow-ups (salvage heuristics) so skyline + ground-based presets keep pulling BC Advantage data; ADV1N35/ADV1N40/ADV6N7 are already wired.
    2. Field Notes (`FNPC17/19/21/28`, `FNSF8/9/11/34`) to capture operational constraints (trail spacing, payload caps, safety-driven slope limits) that influence productivity model parameters.
    3. Technical Notes/Reports (`TN123–TN296`, `TR94`, `TR109`, `TR2017N34`, `TR2017N57`, `TR2021N93`, `TR2023N17`) to extract regression-ready formulas (especially those with explicit forwarder/skid-forwarder models) plus any modern tethered-forwarding insights.
  - After each wave, update `notes/reference_log.md` with abstracts + productivity leads, then backlink actionable findings here (Forwarder coverage) so we know when to extend `fhops.productivity.forwarder_bc` beyond the current AFORA/ALPACA + Kellogg set.
  - remove duplicate fpinnovations reports lurking in `notes/reference` (cross reference with `notes/reference/fpinnovations` and the `reference_log.md` planning doc).

### Skyline alternatives (Ünver-Okan 2020 / Lee et al. 2018)
- [x] Extract coefficients from `/notes/reference/unver.pdf` (Ünver-Okan hill-skidding regressions already implemented) and `/notes/reference/Productivity and cost ... South Korea.pdf` (Lee et al. 2018 HAM300 uphill/downhill regressions live in `fhops.productivity.cable_logging`).
- [x] The helpers already expose the estimators (Ünver cable skidding + Lee skyline); remaining work is to document assumptions/caveats, tie them into telemetry, and ensure CLI warnings for non-BC sources are clear.
- [x] Add telemetry tagging when non-BC skyline models (Ünver/Lee) are selected so downstream consumers know the provenance (CLI now exposes `--telemetry-log` for cable/sk skyline commands, recording model + provenance + warning flag).
- [x] Update docs/how-to sections describing the non-BC skyline/tethered helpers and reiterate the assumptions (spruce uphill skidding in Turkey, South Korean tethered yarder case study, etc.).

### Appendix 5 normalization
- [x] Re-extract the landscape pages (confirmed orientation issue) and normalize into `data/reference/arnvik/appendix5_stands.json` via `scripts/build_appendix5_reference.py` (numeric stand age/volume/DBH + slope percent now recorded alongside the original text).
- [x] Updated `fhops.reference.arnvik_appendix5` to load the new dataset (dataclass carries both text + parsed numeric fields) and refreshed `appendix5-stands` CLI output to show age/volume/DBH/operator counts; new `tests/test_reference_appendix5.py` assertions cover slope percent + typed fields.
- [x] CLI coverage (`fhops dataset appendix5-stands --author ...`) and tests (`tests/test_reference_appendix5.py`) already exercise the normalized stand data; docs now describe how skyline/cable helpers consume the profiles.

### Cross-cutting tasks
- [ ] Update planning docs (`notes/dataset_inspection_plan.md`) and roadmap to reflect the above milestones and dependencies.
- [ ] Expand docs/how-to sections describing the new productivity helpers and Appendix 5 loader; include assumptions table and CLI examples.
- [ ] Refresh fixtures/tests impacted by new productivity defaults (playback/KPI outputs if production shifts) and document any non-BC source caveats in `CHANGE_LOG.md`.
- [ ] After implementation, rerun `pytest` + CLI smoke commands (`fhops dataset estimate-productivity`, `fhops reference appendix5-stands`) and capture telemetry snapshots to ensure reporting hooks continue to work.
- [ ] **CLI/Lint debt cleanup**
  - [x] Skyline productivity CLI now imports the Lee (2018) / TR125 helpers via `fhops.productivity`; `tests/test_cli_dataset_skyline.py` exercises the CLI for both models to keep Ruff in check.
  - [x] Removed the unused `_machine_cost_snapshot` assignments from `validate`, `build-mip`, `solve-mip`, and `evaluate` so Ruff stops flagging F841 while solver/telemetry commands continue to log machine-cost context.
  - [x] Dropped the dead `primary_index` local in `fhops.reference.arnvik_appendix5`’s slope parser so lint passes without suppressions.
- [ ] **Type-check backlog (mypy)**
  - [x] Scenario loader now casts CSV rows to `dict[str, object]` explicitly and uses `_coerce_float` before validation so mypy recognises the numeric inputs.
  - [x] Telemetry report rendering coerces every column to `str`, and the dataset cost CLI asserts non-null forwarder/Kellogg inputs plus separates deterministic vs. RV productivity so `prod` typing no longer conflicts.
- **FPInnovations reference batch catalogued**
  - `notes/reference_log.md` now covers the Advantage, Special Report, Handbook, Technical Report, Field/Forest Note, and cable-yard (FNCY) series (all but the OCR-stubborn FNCY14). High-priority sources for the registry/costing helper include SR54 & TR75 (coastal grapple yarders), TR119/TR125 (skyline + partial-cut productivity/cost), TR106/TR108 (interior CTL vs. tree-length systems), TR2016N46 (modern winch-assist harvester), SR89/TR103 (steep-slope ground skidding + soil-disturbance mitigation), HB12 (system catalog), and SR49/SR85 (equipment planning + partial-cut comparisons). TR112 doesn’t publish regression coefficients in the accessible tables (only descriptive productivity + costing), so we rely on alternate skyline models there; TR127’s Appendix VII *does* contain regression coefficients for delay-free skyline cycle times, so transcribing those is the next actionable step before overlaying alternate sources (Ünver-Okan 2020, Lee et al. 2018) for cases where BC measurements remain missing.
   - Task list moving forward:
     1. [x] Extract Appendix VII regression tables into a structured JSON (`data/reference/fpinnovations/tr127_regressions.json`) via `scripts/build_tr127_regressions.py` (6 block-specific models with coefficients, ranges, intercepts, std. errors, obs, R²).
     2. [x] Implement helper functions (inline with `fhops.productivity.cable_logging`) that load the JSON and expose `estimate_tr127_cycle_minutes(block, sd, latd, logs)` / `estimate_tr127_productivity(block, payload_m3, sd, latd, logs)`—blocks 1–4 only require the listed predictors; blocks 5–6 also include `logs`. Enforce the published ranges and emit warnings when queries fall outside them.
     3. [x] Update `fhops.productivity.__init__` and `fhops.dataset estimate-skyline` to expose the TR127 variants (e.g., `--model tr127-block5`), printing the source + applicable ranges. Add regression tests feeding the Appendix example (Block 5 at SD=365 m, LATD=16 m, LOGS=3 should yield ≈6.39 min cycle time) to validate the helper/CLI path.
     4. [x] Document the new TR127 reference + helper in `CHANGE_LOG.md` and the data-contract guide, reiterating that TR112 lacks regression coefficients so future work doesn’t chase missing data again.
- **BC grapple yarder helpers implemented**
   - Added `fhops.productivity.grapple_bc` exposing SR54 (Washington 118A bunched) and TR75 (Madill 084, bunched vs. hand-felled) productivity equations and registered pytest coverage. These regressions now replace the plantation-derived Spinelli placeholder when estimating CTL grapple productivity; next follow-up is to wire them into the registry metadata and costing helper plus extend coverage with TR112/TR127 skyline data.

## Immediate Next Tasks (queue)
- Extract grapple yarder/skidder regressions from SR54, TR75, TR112, and TR127 (turn length vs. payload) so we can replace the interim Spinelli yarder placeholder; only chase Han & George if BC/FPInnovations coverage still has gaps.
- [x] Finalise the ADV1N12 integration: `thinning_adv1n12_forwarder` / `thinning_adv1n12_fulltree` harvest systems now pre-fill the new forwarder/skidder models + extraction distances, the costing helper pulls the Appendix 1 Valmet/Timberjack splits (inflated to 2024 CAD), and docs reference the presets so analysts know how to run the road-spacing sensitivity directly from the CLI.
- Expand Appendix 4/5 normalization to capture operator, machine weight, slope/payload applicability so the FPInnovations datasets map cleanly into the registry schema.
- Pull skyline/tethered/partial-cut coefficients from TR119, TR125, TR2016N46, SR85, and HB12; keep Visser/McNeel/West/Renzie on deck for supplemental coverage. (Next step: focus on TR119/TR125 for skyline travel regressions.)
- Encode TR119 partial-cut productivity/cost anchors: transcribe Table 7/8 so the costing helper can apply retention-level productivity multipliers and $/m³ defaults when scenarios flag 65%/70% retention or strip cuts. Use these ratios with the Lee/TR125 regressions to approximate BC partial-cut performance until detailed regressions surface. (`notes/reference/fpinnovations/tr119_yarding_productivity.json` now stores the PMH/SMH productivity, costs, and volume multipliers per treatment.)
- Wire the TR119 multipliers into the skyline helper/CLI so partial-cut scenarios (strip / 70% / 65%) automatically scale Lee/TR125 productivity outputs and report the associated $/m³ yarding costs.
- **OpCost-style machine-rate dataset plan**
   - [x] Define the schema for a default machine-rate table (`machine_name`, `role`, `ownership_cost_per_smh`, `operating_cost_per_smh`, `default_utilization`, `move_in_cost`, `source`, `notes`). Store it under `data/machine_rates.json` and expose loader helpers.
   - [x] Transcribe core machine classes from Dodson et al. (2015) (feller-buncher, grapple skidder, processor, loader, road grader, etc.) and Hartley & Han (2007) (coastal grapple yarder, swing yarder, tower yarder) with FX/fuel adjustments to BC dollars (document CAD/USD rate and diesel price assumptions).
   - [x] Layer in FPInnovations repair/maintenance survey (Advantage Vol. 4 No. 23: "Repair and maintenance costs of timber harvesting equipment") as optional coefficients so operating costs can be recomputed from utilization hours when users supply custom labour/fuel inputs. CLI: `fhops dataset estimate-cost --machine-role <role>` now assembles owning + operating + (optional) repair allowances, lets users override individual components, and shows the breakdown + FPInnovations reference hours (2002→2024 CPI factor ≈1.56).
   - [x] Implement a costing helper that blends the default rates with scenario overrides (e.g., `fhops.costing.machine_rates.load_defaults()` → `MachineRate` dataclass). Include utilisation scaling and move-in amortization logic per block/system.
   - [x] Wire machine-role defaults into scenario machinery: `Machine` models now auto-fill `operating_cost` from the rental-rate table when missing, the synthetic dataset generator writes roles + costs, and the example `machines.csv` templates include canonical role slugs (`feller_buncher`, `grapple_skidder`, `roadside_processor`, `loader`) so evaluation tooling has consistent metadata.
   - [x] Canonicalised machine-role slugs across harvest systems + solver constraints (`normalize_machine_role`), so hyphenated labels (`feller-buncher`, `roadside processor`, etc.) map to the same machine-rate entries and system jobs; tests cover the new behaviour.
   - [x] Documented the defaults (sources, conversion factors, utilisation) in the data-contract guide, including explicit instructions for overriding rates via CLI (`--owning-rate`, etc.) or dataset JSON/CSV edits so scenarios stay in sync with the costing helper.
- **Task queue (current sprint)**
   - [x] Document the machine-rate workflow (default CAD assumptions, FPInnovations repair, CLI usage examples) in `docs/howto/data_contract.rst` + CHANGE_LOG entry.
   - [x] Wire machine-rate loader into scenario/system configs so costing/evaluation modules can pull role defaults without manual CLI glue (scenario `Machine` validator now backfills from `data/machine_rates.json`, the synthetic generator writes canonical roles + rates, and harvest-system sequencing consumes the same slug via `normalize_machine_role`).
   - [ ] Normalize Appendix 5 stand metadata (landscape orientation) into JSON with slope/ground descriptors so skyline/tethered helpers can consume it.
   - [ ] Prioritize skyline/tethered helper implementation using Ünver-Okan 2020 + Lee et al. 2018 while TR112/TR127 remain unavailable; capture assumptions + TODOs for replacing the approximations later.
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
