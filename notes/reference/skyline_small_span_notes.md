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

## Pending extractions

- **TN-39 – 26 coastal log-sort operations:** need to capture loader/processor/productivity vs. sort complexity for short-span skyline landings (target: ready-to-use loader cost multipliers for micro-corridors).
- **FNG73 – Hi-Skid self-loading truck:** extract winch cycle times, payload (12 m³), 100 m reach—useful for short-yard/forwarder hybrid modelling.
- **TN-173 – Eastern Canada cable yarding (Ecologger, Christie, Télétransporteur, etc.):** capture per-system spans, payloads, productivity, and cost ($/m³) to benchmark non-BC micro-yarders; these can become alternative presets or validation cases.
