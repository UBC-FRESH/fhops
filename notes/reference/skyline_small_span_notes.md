Skyline Micro-Yarder Reference Notes
====================================

Purpose: collect regression-ready parameters from small-span skyline / short-yard systems so we can extend the helper beyond large Madill/Cypress towers. Each subsection lists the key productivity/cost observations plus any next steps needed before wiring into FHOPS.

## TN-54 – Model 9 Micro Master yarder (Vancouver Island clearcut, 1981)

Source: `notes/reference/fpinnovations/TN54.PDF`

- System: 9 m pipe tower on Timberjack 404 skidder, four drums (skyline/mainline/haulback/slackpuller), two-person crew (engineer/chaser + rigging slinger). Modified skidder skyline configuration (skyline through top block, mainline through slider block, chokers knotted directly). Typical clearcut span ~140 m due to layout, contractor reports 260 m optimal for smallwood thinning; manufacturer plans 600 m with intermediate supports.
- Shift-level stats (16 shifts, 1800.6 m³ total):
  - Availability 94 %, Utilisation 89 % (`notes/reference/fpinnovations/TN54.PDF`, Table 2).
  - Average per shift: 112.5 m³ (39.7 cunits), 246 pieces with average net piece volume 0.46 m³ (16.2 ft³) from weigh-scale reconciliation (Table 4). Per man-day = 56.3 m³.
  - Road-change time averaged 29 min; line-only change ≈24 min, full move ≈51 min (45 total changes).
- Detailed time study (201 turns, piece scale sample of 231 stems, avg fresh volume 0.62 m³, SD 0.45 m³):
  - Average cycle time 5.96 min (pro-rated road changes + minor delays included). Composition: Hookup 2.27 min (38 %), Outhaul 0.29 min, Inhaul (lateral + direct) 0.56 min, Decking 0.17 min, Unhook 0.72 min, Road-change allocation 1.06 min, Delays 0.89 min (Table 5 & Figure D).
  - Average pieces/turn 3.2; average turn volume 1.98 m³ (70 ft³). Productivity ≈19.8 m³ PMH (10 turns/h). Yarding distance observed average 71 m (233 ft).
  - Observed line speeds: Outhaul 4.1 m/s (803 ft/min), Inhaul 2.1 m/s (416 ft/min). Hookup delay partly due to lightweight chokers and mainline clutch rub; ~9 % of hookup time spent waiting for chokers to drop.
- Cost/crew context: crew of two (engineer also chaser); loader/skidder used to clear decks but not counted in yarder cost. Machine cost $94 k (1982 CAD). Frequent minor repairs (clutch adjustments, brake line, mainline knot failures) but average repair time 12–15 min thanks to experienced crew.
- Data readiness:
  - We can treat the 5.96 min cycle as baseline with a constant component (Hookup+Decking+Unhook ≈3.16 min) plus distance-sensitive component derived from line speeds (time ≈ (distance / 4.1 m/s) + (distance / 2.1 m/s)). Road-change allocation adds 1.06 min per turn; delays 0.89 min can be parameterised via utilisation.
- Need to digitise piece-size distribution (Figure E) for a more refined payload model, but mean/SD already captured.
- Action: convert above into JSON entry (e.g., `data/reference/skyline_micro_master.json`) with fields for cycle constants, line speeds, average payload, crew size, and cost notes so the helper can expose a “micro_master_clearcut” preset.

## TN-39 – Coastal BC dryland sortyards vs water-sorting grounds (1980 snapshot)

Source: `notes/reference/fpinnovations/TN39.PDF`

- Scope: 26 coastal log-sorting sites (18 dryland sortyards, 8 water-sorting grounds) split into four throughput bands (0–60 kccf, 61–160 kccf, 161–260 kccf, 261–500 kccf; 1 kccf ≈ 2 831.7 m³). Data includes land/water footprint, labour, equipment, bundling %, and 1980 CAD costs.

### Dryland sortyard averages (all size classes)

- Annual throughput: 182 625 ccf ≈ 517 000 m³; 268.5 shifts/year (8 h) → 2 147 operating hours.
- Bundling: 96 % of output, 12.5 average sorts, bundle size ≈ 12.2 ccf, bundle-boom section 92 ccf.
- Land utilisation:
  * Sorting acreage: 16.32 ac (6.60 ha) overall average; rises from 3.9 ac for <60 kccf to 22 ac for 161–260 kccf then down to ~19.6 ac for >260 kccf thanks to higher efficiency.
  * Land storage acreage: 6.65 ac average (2.69 ha); storage intensity ~7.07 acres water when on-land? (Table 4 shows land storage + water storage).
  * Sorting productivity: 23 377 ccf sorted per sorting acre annually (≈66 200 m³/ha).
- Labour/productivity: 30 029 manhours/year; 24-person average crew → 33.63 ccf/manday (≈95 m³), 57.3 pieces/manday. Average shift moves 1 514 pieces (≈832 ccf).
- Equipment utilisation: 11.6 sorting machines avg; 16.74 pieces/machine-hour; 2.17 annual manhours per machine-hour.
- Costs (1980 CAD): Operating $5.41/ccf, custom sorting $0.23/ccf, ownership $1.18/ccf → total $6.82/ccf (~$2.41/m³). Capital intensity: $7.61 invested per cunit (~$2.69/m³). Re-hauled yards incur extra $1.9–$5.1/ccf depending on distance.
- Storage intensity roughly independent of incoming volume; driven instead by mill pull, booming capacity, and transport mode. High bundling ratios cut sinker loss (major eco justification vs water sorting).

### Water sorting averages (for contrast)

- Annual throughput: 210 393 ccf (≈596 000 m³), 252.8 shifts/year.
- Bundling share only 48 %, 12 sorts on average.
- Water footprint: 88 water acres total (36 ha) split approx 9 ac sorting, 21 ac booming, 71 ac storage; flat rafts demand 72 % more area than bundled booms.
- Productivity comparable to dryland: 33.29 ccf/manday but lower pieces/shift (~2 023 ccf per shift). Cost advantage ($6.82 vs $10.41/ccf) offset by higher sinker loss, less accurate scaling/grading, and aquatic impacts.

### Key takeaways for skyline planning

- Sorting area requirement scales more with pieces/shift than volume/shift. If skyline presets push piece size down (higher pieces/turn), dryland yard footprint must grow to handle the extra sorting area.
- Presorting (truck or bundle) shrinks required acreage and lowers cost per cunit; bundling at the sortyard yields 70 % more boom volume than loose flats, freeing water area. Non-presorted inflow drives higher land requirement.
- High bundling rates (96 %) + on-land scaling justify dryland yards despite $3.59/ccf (~$1.27/m³) cost premium over water-sorting; savings come from reduced sinker losses, better grade control, and ability to remanufacture logs before skyline backhaul.
- For skyline micro-yard planning, use the 0–60 kccf bracket (small yard) as baseline: ~3.9 sorting acres (1.58 ha), 93.7 % bundling, 11 sorts, 477 ccf shift throughput (~1 350 m³). Helps size compact skyline corridors and staging footprints.

## FNG73 – Hi-Skid short-yarding, self-loading truck (Maple Ridge demo, 1998)

Source: `notes/reference/fpinnovations/FNG73.pdf`

- System overview: truck-bed track with travelling fairlead, 100 m of 13 mm mainline, and chain-based self-dump mechanism so the same vehicle can yard, load, haul, and unload without extra equipment. Breakaway block strapped to residual trees auto-releases and trails the rigging back, letting the operator “snake” turns around obstacles.
- Specs: winch speed 69 m/min; base line pull 18.8 kN (upgradeable to 26.7 kN). Payload 12 m³, log length designed for ≤6.5 m but deck can be extended. Truck GVW 15 250 kg; prototype price CAD 50–60 k (1999). Remote control allows a single operator to hook chokers, yard, and load; truck strapped to roadside tree until payload counterweights skyline forces.
- Demo setting: BCIT Woodlot 007 (Maple Ridge CWHdm), 70‑year hemlock/cedar/fir, DBH 22 cm, heights ~35 m, 0–10 % slopes, heavy obstacles (stumps, windthrow) and thick moss. Trees hand-felled, delimbed/topped in-stand; near-road stems bucked to 5.6–6.86 m, remote stems brought out tree-length then bucked roadside.
- Productivity snapshot (20 timed cycles): average yarding distance 30 m (max 80 m), piece volume 0.24 m³, yard+load rate 4.16 m³/h. Including 15 min haul to dump + unload, expect one 12 m³ load roughly every 4 h (~24 m³ per 8 h shift). Anchoring strap + breakaway block mitigate hang-ups, but operator occasionally frees logs manually when obstacles pinch the turn.
- Operating tips: partially activating the chain-dump cylinders during loading recentres slippery logs so they clear the lateral track members; tree-length stems must be unhooked/bucked roadside before loading. Wrappers applied before travel; pivoting stakes released during dump so chains slide the load off.
- Use cases: short-corridor salvage or riparian/machine-free buffers where corridor construction is forbidden; urban tree removal; micro blocks <100 m from roads/trails. Breakaway block protects leave trees, remote control keeps operator on road.
- Dataset/helper coverage: `data/reference/fpinnovations/fng73_hi_skid.json` stores the observed payload, line speeds, cycle elements, and travel allowances; `estimate_hi_skid_productivity_m3_per_pmh` + `fhops dataset estimate-skyline-productivity --model hi-skid [--hi-skid-include-haul]` now expose the yarding vs. haul-adjusted productivity (defaults to 4.16 m³/PMH at 30 m spans, warns past the 80–100 m envelope). The `cable_micro_hi_skid` harvest system reuses these defaults, and `data/machine_rates.json` now carries the derived `skyline_hi_skid` entry (ownership 11.5 + operating 55 $/SMH in 1999 CAD, based on a CAD 60 k attachment amortized over 5 years + the June 15 1999 IWA log-truck driver wage of 24.01 $/h + 38 % benefits per ADV2N62). `--show-costs` therefore cites a dedicated short-yard truck rental instead of the Gabriel proxy.
- Helper TODO: confirm the Hi-Skid cost entry with Alfa Fab or FPInnovations bookkeeping (current rate references ADV2N62 wage tables, assumed attachment depreciation, and a light fuel/maintenance allowance) and pull a CPI trail so future updates can re-inflate to 2024 CAD without re-deriving the components.

### Hi-Skid cost/CPI references

- **Base year** – The machine-rate entry keeps the 1999 CAD base so the CLI can inflate via `fhops.costing.inflation` (StatCan Table 18-10-0005-01 machinery/equipment CPI). No manual multiplier is embedded; instead `inspect-machine --machine-role skyline_hi_skid` now prints both the 1999 column and the CPI-adjusted 2024 equivalent.
- **Owning column (11.5 $/SMH)** – Derived from a CAD 60 k attachment price (FNG73 prototype quote) amortised over 5 years at 1 200 SMH/yr with 10 % salvage and 8 % interest+insurance. Numbers live in the JSON so scenario/telemetry can audit the assumption.
- **Operating column (55 $/SMH)** – Broken into: single operator using the ADV2N62 Appendix II June 15 1999 IWA wage (24.01 $/h + 38 % fringe = 33.13 $/SMH), diesel at 8 L/h × 0.65 $/L = 5.2 $/SMH (same fuel assumption as the Field Note), plus 16 $/SMH for tires, hydraulics, chokers, and rigging wear. Remainder (≈0.7 $/SMH) covers incidental lubricants.
- **Move-in (2 000 $)** – Mirrors a short lowbed mobilization for the truck-mounted attachment and matches the move charge we already use for other micro systems.
- **Next verification step** – Reconcile these assumptions against any Alfa Fab / FPInnovations invoice if it ever surfaces; until then we treat ADV2N62 + the Field Note as the authoritative wage/fuel references.

## TN258 / FNCY12 – Thunderbird TMY45 + Mini-Mak II (intermediate supports, Salmon Arm BC, 1992)

Sources: `notes/reference/fpinnovations/FNCY12.pdf`, `notes/reference/fpinnovations/TN258.PDF`

- System overview: Thunderbird TMY45 swing yarder (13.7 m tower, Cummins 220 kW) running a standing skyline with gravity outhaul, paired with a Maki Mini-Mak II slack-pulling carriage (7.5 kW, 6.8 t payload, 568 kg, passes intermediate supports). Support hardware (two skyline support jacks) cost ≈CAD 33.5 k. Loader (Drott hydraulic), Timberjack 450 grapple skidder, and Cat D8 provided landing support.
- Setting: Stukemapten Lake, north of Salmon Arm. Slopes 30–70 % (avg 55 %), gross volume 372 m³/ha dominated by Douglas-fir (81 %). About 23 % of the area needed intermediate supports to achieve lift across convex slopes and wet benches.
- Rigging guidance: support trees 50–60 cm DBH spaced ≤6 m, pruned and guyed at 12–22 m heights. Skyline support cable tensioned into an “M” configuration, upper guylines crossed for lateral stability, lateral yarding constrained to ~30 m each side of the skyline to minimize hang-ups. TN-258 backspar stress pilot quantified skyline/guyline tensions during lateral pulls and when carriage/timber passed over the jack.
- Crew & learning curve: yarder operator, chaser, full-time rigger, part-time rigger, two chokersetters (rigging crew time inflated man-day costs vs. standard skyline presets). July output (no supports yet) averaged 102 m³/shift while the crew learned the Mini-Mak; by September/October the system averaged 171–189 m³/shift even when supports were in play.
- Productivity record (Bell Pole Co., July–Oct 1992): 10 139 m³ over 67.5 productive shifts (150 m³/shift overall). Removing the July learning curve and fire-hazard delays yields 166–177 m³/shift. Ten-hour shifts; nine early shifts plus three fire shut-down days included in totals.
- Dataset: `data/reference/fpinnovations/fncy12_tmy45_mini_mak.json` now captures the equipment specs, rigging geometry, lateral limits, skyline/guyline tensions (from TN-258), and month-by-month productivity so long-span/Intermediate-support presets can consume these numbers without re-opening the PDFs.
- Line tension findings (TN-258 Tables 1–2): skyline tensions averaged 88–92 kN with an empty carriage then rose to 101–141 kN when turns were suspended under the carriage (peaking at 155 kN during breakouts and 147 kN on hung-up large turns). Tension dipped back to ~93–102 kN when the carriage passed over an intermediate support because the snake picked up the load. Guyline tensions sat near 12–13 kN with the carriage empty but climbed to 17–24 kN during lateral yarding and up to 37 kN when hang-ups or aborted turns yanked on the critical guyline. Longer lateral pulls (>30 m) were the main trigger for spikes, so we need to flag skyline helpers whenever analysts exceed that envelope.
- Support proxy (since TN-258 lacks timing data): TN-157 reports road-change minutes for seven Cypress 7280B cases; dividing those minutes by yarding minutes yields a **0.25** average ratio (and **0.14** lower quartile). We treat the average as Cat D8 backspar standby per Thunderbird productive hour and the lower quartile as Timberjack 450 trail-support time. Costs come from the TR-45 machine-rate entries (`bulldozer_tr45`, `skidder_tr45`) and inflate automatically when `grapple_yarder_tmy45` is queried.
- Costing status: `grapple_yarder_tmy45` now captures the owning/operating split by converting the LeDoux (1984) TMY-45 hourly charges from USD 1984 → CAD 1992 (StatCan Table 18-10-0005-01 CPI + vector v37426 FX), scaling the labour column to the FNCY12 5.5-person crew (vs. the nine-person residue trial), and amortising the CAD 33.5 k Mini-Mak II + skyline support jack bundle over five years (1 200 SMH/year) so the attachment lives in owning cost. Loader/chainsaw/radio allowances stay aligned with the LeDoux breakout and the Cat D8/Timberjack 450 proxies above are now bundled into the operating column (via the TR-45 bulldozer/skidder roles).
- Remaining wish list: secure an authentic 1992 BC payroll/fuel/repair worksheet for the Thunderbird fleet plus any Jay-Vee Yarding accounting that allocates intermediate-support moves to the D8 vs. rigging crew. The TN258 manuscript does **not** publish intermediate-support setup/move timing or Cat D8/Timberjack utilisation minutes—only the tension envelopes—so revisit the 0.25/0.14 SMH proxies once better data surfaces.
- Intermediate-support timing cross-check (2025‑11‑30): Re-read TN258 (pdftotext excerpt above) and confirmed it only reports static/dynamic line tensions (Tables 1–2) plus rigging geometry—no Cat D8/Timberjack utilisation, setup minutes, or per-support cycle timing. The proxy ratios already baked into `data/reference/fpinnovations/fncy12_tmy45_mini_mak.json` (`cat_d8` = 0.25 SMH/SMH, `timberjack_450` = 0.14 SMH/SMH) therefore remain the best-available placeholders, sourced from TN‑157 road-change÷yarding ratios. Keep the note here so future readers know TN258 cannot close that gap without external payroll logs.
- TN157 support-ratio sanity check (2025‑12‑01): recomputed the TN157 road-change minutes ÷ yarding minutes for all seven cases to anchor the TN258 proxies. Ratios ranged 0.085–0.508 with a mean of 0.247 and median 0.224 (Q1 = 0.137, Q3 = 0.333). Backspar-specific work (Hitachi UH14) consumed ≈58 % of total road-change minutes overall, swinging from 5 % on the shortest corridors to 99 % on the longest partial cuts. These stats justify keeping the Cat D8 standby allowance at 0.25 SMH/SMH (matches the TN157 mean) and the Timberjack trail-support allowance near the lower-quartile 0.14 SMH/SMH. Reference table:

  | Case | Yarding min | Road-change min | Ratio road/yard | Backspar share |
  | --- | --- | --- | --- | --- |
  | 1 | 455.6 | 38.9 | 0.085 | 0.08 |
  | 2 | 412.2 | 92.4 | 0.224 | 0.05 |
  | 3 | 392.0 | 199.1 | 0.508 | 0.58 |
  | 4 | 764.0 | 254.6 | 0.333 | 0.33 |
  | 5 | 1 277.5 | 175.1 | 0.137 | 0.73 |
  | 6 | 544.5 | 141.9 | 0.261 | 0.86 |
  | 7 | 924.7 | 164.4 | 0.178 | 0.99 |

  (Backspar share = backspar_minutes ÷ (yarder_minutes + backspar_minutes) using the per-case `road_changes` block in `tn157_cypress7280b.json`.)

## TN82 – FMC FT-180 + JD 550 steep ground alternative (Canal Flats, 1983–84)

Source: `notes/reference/fpinnovations/TN82.PDF`

- Study covers Crestbrook’s contractor-operated FMC FT-180 tracked skidder working with a John Deere 550 crawler on 35–60 % sidehills (summer clearcut) and a winter right-of-way (≤9 % running slope). Trees averaged 0.39 m³ in the clearcut and 1.7 m³ in the ROW.
- Production split (Table S‑1): in the clearcut the FT-180 averaged **8.0 m³/PMH** (20.5 trees, 2.4 turns) or **55.6 m³/8 h shift** vs. the JD 550 at 5.2 m³/PMH (16.3 m³/shift). On the winter ROW the FT-180 reached **17.1 m³/PMH** (108 m³/shift) while the JD handled shorter pulls at 11.4 m³/PMH (43 m³/shift). System-level output was 72 m³/shift (clearcut) and 151 m³/shift (ROW).
- Hours in productive work sat near 80–89 % for both machines; availability ~83–93 %. The tractor absorbed trail-building, decking, and cleanup, while the FT-180 focused on longer skids (often pre-bunched by the JD during cleanup).
- Use this dataset when comparing micro skyline vs. “fast track” ground options: payloads stay small but the FT-180 delivers 50 % more volume per PMH0 than the small crawler. No skyline/slack-puller labour data appears—this is purely a tracked-skidder benchmark.

## TN98 – Handfalling economics (Vancouver Island, 1985)

Source: `notes/reference/fpinnovations/TN98.PDF`

- 10.3 ha, 110‑year second-growth (60 % Douglas-fir, 21 % hemlock, 16 % cedar). Three skilled fallers were time-studied across **1 746 measured trees** (plus 5 328 supplemental observations). Selective bucking: only trees ≥60 cm butt diameter were bucked; smaller stems felled and left for roadside processing.
- Productive time once in-stand ≈70 %; cutting consumed ~40 % of total, moving ≈20 %, limbing/bucking only 4–5 % because roadside processors handled most logs. Average **220 trees/shift** (203 m³) at $319.62/shift labour → **$1.45/tree ($1.57/m³)** overall.
- Regression (Table 6) links cutting time to DBH: `time = -0.0027 + 0.0274·dbh` for Douglas-fir (minutes), similar forms for cedar/hemlock. Table 7 converts to cost: e.g., 12.5 cm stems cost **$0.86/tree ($21.50/m³)** vs. 82.5 cm stems at **$3.65/tree ($0.49/m³)**. Cedar/Douglas-fir generally highest cost per cubic metre; hemlock/deciduous lowest.
- Use these curves to parameterize manual-falling cost/planning knobs inside skyline presets (e.g., salvage corridors requiring handfallers). The report includes per-diameter cutting times, limbing/bucking additions, and fixed delay (0.83 min/tree) but no slack-puller labour data (pure falling study).
- Data file: `data/reference/fpinnovations/tn98_handfalling.json` captures the regression coefficients, per-diameter cost/time tables, and labour/CPI context so helpers can ingest the dataset directly.

## TN-173 – Eastern Canada compact skyline fleet (Ecologger, Gabriel, Christie, Télétransporteur, Timbermaster)

Source: `notes/reference/fpinnovations/TN173.pdf`

- Study scope: 1991 time-and-motion review of five light cable systems working short spans (mostly 90–240 m) in eastern Canada partial cuts. Each case logs yarding distances, payload, crew mix, availability, and a full cost build (1991 CAD) split into owning vs. operating.
- RMS Ecologger: radio-controlled tractor carriage with skyline + mainline drums, two-person rigging crew. Average payload 0.34 m³, cycles dominated by hookup (38 %) at short distances. Delivered ≈24 m³/PMH₀ with direct costs ~$22.40/m³. Excels in tight corridors where guyline anchoring options are limited.
- Gabriel truck yarder: rear-mounted tower with 150 m skyline, payload 0.16 m³ (pre-commercial stems). Productivity capped near 14 m³/PMH₀ because chokers seldom exceed two pieces per turn, but road mobility keeps move-in cost low. Operating cost floor ~$20.69/m³; ideal for quick salvage or ROW brushing.
- Christie monorail skyline: structural mast plus self-propelled carriage; larger 0.49 m³ pieces from patch cuts. Highest payload in the study and ~30 m³/PMH₀ on ≤180 m spans, but requires longer road-change/setup (guyline plan + intermediate supports). Costs climb to $27.92/m³ when spans push beyond 220 m due to extra anchors.
- Télétransporteur: truck-mounted tower with carriage that can shuttle logs over road gaps. Turn volume 0.21 m³, labour-intensive outhaul (three rigging crew) but excellent deflection control for riparian buffers. When spans stay <150 m it matches Ecologger productivity; beyond that, outhaul delay knocks utilisation down to 0.63.
- Smith Timbermaster: trailer tower paired with 5/8″ skyline and 1/2″ mainline; piece size 0.28–0.54 m³ depending on block. Achieved 26–32 m³/PMH₀ on 120 m spans and maintained hook times by using mechanical slack-pullers. Mobility is slower than truck yarders but still <3 h per road change.
- Cross-system takeaways: labour-corrected (“hot”) productivity averaged ~3 m³/PMH per worker, so presets need to scale output with crew size if analysts deviate from the study crews. Direct costs ranged $20.69–$27.92/m³; most variance came from setup/move frequency rather than mechanical utilisation. The data provides payload + distance envelopes for non-BC micro-yard presets (e.g., `ecologger_short_span`, `timbermaster_patch_cut`) and cost references for when BC CPI-adjusted rates are missing.
- Dataset: `data/reference/fpinnovations/tn173_compact_yarders.json` now holds the per-system cycle stats, distance/slope ranges, crew sizes, productivity, and $/PMH components so the skyline helper can consume these cases directly (Ecologger, Gabriel, Christie, Télétransporteur, Timbermaster 1984/1985).
- Machine-rate coverage: `data/machine_rates.json` ships matching entries (`skyline_ecologger_tn173`, `skyline_gabriel_tn173`, `skyline_christie_tn173`, `skyline_teletransporteur_tn173`, `skyline_timbermaster_tn173`, `skyline_hi_skid`) so `--show-costs`/harvest-system overrides can cite the Eastern hourly rates or the derived Hi-Skid truck rental (ownership 11.5 + operating 55 $/SMH in 1999 CAD).
- CLI coverage: `fhops dataset estimate-skyline-productivity --model tn173-ecologger|tn173-gabriel|tn173-christie|tn173-teletransporteur|tn173-timbermaster-1984|tn173-timbermaster-1985` now pulls the structured defaults, prints observed vs. computed productivity, and warns when slope distances exceed the recorded TN173 span envelope.
- Harvest-system coverage: `default_system_registry()` now exposes `cable_micro_ecologger|gabriel|christie|teletransporteur|timbermaster` (TN173 presets) plus `cable_micro_hi_skid`, so `--harvest-system-id` (or dataset blocks referencing those IDs) auto-select the correct skyline model + machine-rate role.
- Helper TODOs:
  - Feed the new micro presets into the synthetic/contract generators (so sample scenarios rotate among the TN173/Hi-Skid systems) once the `skyline_hi_skid` CPI audit trail is documented.
  - Move on to TN258/FNCY12 span-penalty wiring now that Thunderbird TMY45 + Mini-Mak costing exists; need intermediate-support timing + Cat D8 standby assumptions before presets/scenarios can auto-toggle the support penalty.

## Pending extractions

- **TN258 – Thunderbird TMY45 + Mini-Mak II:** costing gap is closed (see `grapple_yarder_tmy45`), but we still need the detailed intermediate-support timing + D8/Timberjack utilisation notes so span-penalty wiring can differentiate between “supports up” vs. “no supports” cycles and so the dozer standby cost can move from a narrative reminder into the preset.
- **TN82 / TN98 – small skyline and manual support studies:** triage for additional compact-span payload distributions and slack-puller labour requirements to round out the micro-yarder helper backlog.

## Next Actions (micro-skyline queue)

- [x] **Document skyline_hi_skid cost provenance** – See “Hi-Skid cost/CPI references” above for the amortisation + wage/fuel breakdown now cited by `inspect-machine --machine-role skyline_hi_skid`.
- [x] **Scenario coverage** – `src/fhops/scenario/synthetic/generator.py` tier mixes now include every `cable_micro_*` preset plus Hi-Skid, so the synthetic generator randomly seeds those harvest systems (and their skyline overrides/machine-rate hooks) into sample scenarios across the small/medium/large tiers.
- [x] **Hi-Skid CPI trail in planning docs** – `notes/reference/bc_iwa_wage_tables.md` now has a dedicated 1999 entry (ADV2N62 + 38 % fringe) explaining the labour/fuel/ownership assumptions backing `skyline_hi_skid`, so CPI updates can cite the source directly.
- [x] **TN258 intermediate-support timing** – Verified (via TN258 text) that the pilot study only presents skyline/guyline tension observations and structural analysis; no intermediate-support timing or support-machine utilisation exists. The Cat D8/Timberjack standby ratios therefore stay proxy-only (documented in `fncy12_tmy45_mini_mak.json`) until authentic payroll sheets surface.
- [ ] **TN82/TN98 extraction** – Pull payload/distance/slack-puller labour tables from these early-80s skyline studies and add them to the dataset vault to expand the non-BC micro preset palette (especially for manual-support corridors).
