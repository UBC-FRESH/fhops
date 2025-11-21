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
- Helper TODO: build a `hi_skid` preset capturing payload (12 m³), base yarding productivity (4.16 m³/h across 30 m spans), optional obstacle/terrain multipliers, and travel/dump allowances (≈0.5 h per haul). Need ownership/operating cost assumptions (truck + attachment) before linking to `--show-costs`.

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
- Helper TODOs:
  - Thread the TN173 $/m³ owning vs. operating splits into `data/machine_rates.json` as interim “non-BC reference” entries, tagged so `--show-costs` can cite the regional origin.
  - Wire the new JSON cases into skyline presets/harvest-system overrides (`ecologger_short_span`, `gabriel_salvage`, `teletransporteur_hot_yard`, `timbermaster_patch_cut`) and surface the recommended span caps.
  - Flag the span sensitivity (productivity drop beyond ~200 m) inside harvest-system overrides so scenario generator warns when analysts stretch these systems past the tested envelope.

## Pending extractions

- **TN258 – Thunderbird TMY45 + Mini-Mak II:** need the intermediate-support timing, guyline tension envelope, and any embedded costing references so the TMY45 preset can inherit productivity and owning/operating splits without relying on Skylead proxies.
- **TN82 / TN98 – small skyline and manual support studies:** triage for additional compact-span payload distributions and slack-puller labour requirements to round out the micro-yarder helper backlog.
