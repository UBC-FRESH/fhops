# Gavin Lake — Beaver Valley MDWR no-clearcut / group-selection screen

Status: **constraint-translation screen, not an approved plan or compliance
determination.**

## Constraint

The 2007 AFRF Management and Working Plan #3 makes mule-deer winter range the
primary objective in the Beaver Valley working circle:

- Beaver Valley MDWR: **2,799.31 ha**, **1,443 blocks**;
- **no clearcut** in the MDWR;
- group selection with a **40-year re-entry**;
- Table 30 pass intensity by habitat class: **High 33%**, **Moderate 25%**,
  **Low 20%**;
- maximum group size **0.4 ha on warm aspects** and **0.7 ha on other aspects**.

The current public Gavin policy screen (`gavin-policy`) does not carry the
constraint: it schedules 2,759 ha of MDWR and all 8,980 events are clearcut.
This screen replaces clearcut with group selection on MDWR tracks and reports
the production consequence.

## Habitat classes

The public BC long-term habitat objective map for Beaver Valley North (Prouton
Lakes), dated 6 December 2001, has been digitized. It gives a fine-scale
High/Moderate/Low split for the MDWR that is very different from the legacy BEC
proxy:

| Class | BEC proxy | Official fine map | Model class area |
| --- | ---: | ---: | ---: |
| High | 14.27 ha | 682.3 ha | 600.0 ha |
| Moderate | 213.06 ha | 1,115.4 ha | 1,082.1 ha |
| Low | 2,571.98 ha | 898.4 ha | 1,117.2 ha |
| Unclassified | — | 103.3 ha | — |

The official polygons cover 84.6% of the MDWR block area. The model-class
column applies the 50% block-coverage floor and the BEC fallback for
unclassified edge blocks.

The 2007 MWP #3 says the Appendix 9 class distribution was adjusted to coincide
with the total-chance harvest blocks. That **adjusted compartment map is still
a separate legal review step**; this screen uses the finer BC long-term
objective polygons, not a legal compartment map. The 2007 legal order and
current UWR boundary also still need review.

## Method

- Clone the legacy tracks used by MDWR fragments.
- Remove clearcut from the MDWR clones.
- Add Table 30 group-selection treatments at the official fine-map class
  intensity.
- First entry at age 80; **40-year re-entry** after that.
- Preserve the fragment age across partial cuts. The matrix uses a
  negative-offset sentinel so a group-selection pass does not reset a stand to
  age zero.
- Scale product yield, treated area and carbon removal by the pass fraction.
  The block remains a full-area partial-cut volume screen rather than a
  spatial group layout.
- Run the translated 300-year schedule against the existing public Gavin policy
  target set (174,000 m³ per period, 600,000 m³ period-30 stock floor, ±4%
  even-flow).

## Results

| Scenario | MDWR clearcuts | Total production | Mean period | Min period | Max period | Period-30 stock | Targets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `gavin-policy` | 4,352 events / 2,759 ha | 5.385M m³ | 179,505 m³ | 174,070 m³ | 187,575 m³ | 610,004 m³ | 61/0/0 |
| `gavin-mdwr` official fine-map, 40-year re-entry | **0** | **5.626M m³** | **187,519 m³** | **81,358 m³** | **377,744 m³** | **1,493,175 m³** | **15/33/13** |
| Official fine-map, current BA ≥ 40 m²/ha | **0** | **4.592M m³** | **153,075 m³** | **79,713 m³** | **269,628 m³** | 1,493,175 m³ | **14/35/12** |
| Official fine-map, temporal BA ≥ 40 m²/ha + 0–9 year stagger | **0** | **4.154M m³** | **138,466 m³** | **92,765 m³** | **219,971 m³** | 1,493,175 m³ | **13/37/11** |
| Prior BEC first-entry screen | 0 | 3.735M m³ | 124,508 m³ | 80,704 m³ | 201,462 m³ | 395,682 m³ | 10/43/8 |
| MDWR deferral floor (prior run) | 0 | 3.560M m³ | 118,678 m³ | 64,963 m³ | 151,070 m³ | 1,493,175 m³ | 8/47/6 |

The corrected 40-year re-entry screen produces **more cumulative volume** than
the prior first-entry screen. It is still not a like-for-like comparison with
the timber-only clearcut policy: the partial-cut curves repeatedly harvest a
fraction of a full-area stand curve, so the 5.626M m³ total is a screening
upper bound, not a final yield forecast.

The target status is reported against the existing 174k policy target set. It
is a **trade-off result**, not a failure hidden by a redefined target.

## Re-entry audit

The earlier MDWR clone reset the fragment age to zero on every pass, while the
pass product curves start at age 79. In a block test, the first pass produced
volume and every later 40-year pass produced zero. The corrected matrix
preserves fragment age across each pass; block 266 now yields on every
40-year entry.

The prior **3.735M m³ / 10/43/8** line is retained above only as the superseded
first-entry result. It must not be cited as a validated 40-year re-entry
result.

Details:
`notes/2026-11-18_gavin-mdwr-official-habitat.md`.

## Legal-order caveat

The current screen uses the 2007 MWP #3 Table 30 mapping (High 33 / Moderate 25
/ Low 20) and a 40 m²/ha BA gate. The reviewed 2007 Transition/Deep GAR order
instead sets **Low 33 / Moderate 25 / High 20**, **45 m²/ha in ICH and 40
elsewhere**, and a **0.1 ha minimum opening** (0.1–0.3 ha on frost-prone
sites). The current public screen is therefore a scenario screen, not a
legal-order implementation. A legal-order rebuild is the next model change.

## Limits

- The adjusted Appendix 9 compartment map has not been reconciled with the
  fine-scale BC long-term objective polygons.
- The block-level partial-cut curve is a volume screen. It does not lay out
  spatial groups, enforce the 0.4/0.7 ha group-size cap, or simulate
  within-block cohort structure.
- Preparatory thinning at least ten years before group selection is not
  modelled.
- No public AFRF private finance ledger is used or fabricated.
- The 2007 legal order and current UWR boundary still need review.
- The official fine-map georeference is a printed-grid fit, not a survey
  control.

## Legal review

The 2007 FSP Table 7 allows even-aged systems, including clearcutting, on
fresh and wetter sites within the Beaver Valley MDWR. The no-clearcut rule in
this screen is therefore a **stricter policy choice** across the whole MDWR,
not a direct FSP transcription.

BC MDWR Information Note #3 quotes General Wildlife Measure 6 from the 2007
transition/deep snowpack GAR order: group selection requires a pre-harvest
basal area of at least **40 m²/ha**. A separate sensitivity now gates the
official schedule on **current VRI 2025 BA**: 625 blocks / 1,296.8 ha pass,
789 blocks / 1,429.9 ha are held and 29 blocks / 72.6 ha are unknown.
That sensitivity produces 4.592M m³ and 14/35/12 targets. It is a current
snapshot only; future growth and post-pass BA recovery are not modelled.

A temporal ledger then grows each block from its VRI BA using the WS4 volume
curve, checks every candidate entry, deducts the pass fraction after an
accepted cut, and defers entries below 40 m²/ha. The accepted schedule is
staggered by a deterministic 0–9 years by block id, which improves target
performance from 10/39/12 to **13/37/11**. It accepts 1,045 blocks /
2,238.5 ha and holds 398 blocks / 560.8 ha. The BA growth proxy is still a
screening assumption, not a validated basal-area model. The 0.4/0.7 ha caps
and 3–5 cohort structure are still not modelled.

Appendix 9 is a compartment-level adjusted map, not a block-level attribute in
the legacy layer. The fine BC long-term objective polygons used here are not
the adjusted Appendix 9 boundaries. The screen is therefore an official
fine-map volume screen, not a legal compliance determination.

Full review:
`notes/2026-11-19_gavin-mdwr-legal-review.md`.

## Group-size capacity check

A terrain screen on the staggered temporal schedule classifies warm aspects as
slope > 10% and aspect 135–270° (LMH 59), with caps of 0.4 ha warm and 0.7 ha
other. The 2,897 accepted entries cover 1,045 blocks and 1,494.0 ha of cut
area, with a mean minimum group count of 2.39 and a maximum of 18. Terrain
coverage is incomplete for 131 blocks at DEM/block edges, and 276 blocks have no
warm-aspect area.

This is a capacity check only. It does not draw group polygons, enforce a
minimum group size, or model cohort growth.

## Schematic group layout

A 10 m cell prototype was built for the staggered temporal schedule. The full
full group state now covers all 1,443 MDWR blocks: **34,512 groups**, **2,797.5 ha**
and a maximum group area of 0.7 ha. Warm groups are capped at 0.4 ha. Of these,
**9,674 groups / 1,430.3 ha** are assigned to cuts; 24,838 groups remain
standing.

A group-level WS4 run carries every group as a separate block with
`feature.yield.managed.total` and `feature.ba.managed.total`. It produces
0.533M m³ / 300 years, 9,674 group cuts, final standing yield 1,274,641 m³,
initial BA 102,863 m² and final BA 255,737 m². The BA curve is a VRI 2025
per-BEC BA-volume-age fit, not a plantation BA model.

Public group-state prototype: `http://10.232.253.210:8780/fhops/?run=gavin-mdwr-group`.

The consolidated group state covers 2,797.5 ha of the 2,799.3 ha MDWR; the
remaining 1.8 ha gap is spread across 22 blocks and is polygon-edge residue. The aligned group state produces 0.533M m³, versus 0.594M m³ for the
MDWR-only block screen: a ratio of 0.90, or 190 versus 212 m³/ha. The remaining
difference is full-group versus block-fraction accounting. The public group
scenario now exposes the full 2,797.5 ha group-cohort state.

The corrected cohort state inherits the accepted block-level BA gate; GWM 6 is
a stand-level prerequisite, not a per-group test. It records 19,587 accepted
cohort entries, **0.651M m³** harvested, final standing volume **1.168M m³**,
final BA **190,708 m²**, and a group/block ratio of **1.10** (233 versus 212
m³/ha). That is a model-reconciliation result, not a replacement for the block
screen. The group result remains a prototype and does not replace the block
policy screen.

This is a schematic capacity/verification layer, not an operational layout. It
does not enforce a minimum group size, model cohort growth, represent windthrow,
or feed group-specific volume back into WS4. The next step is a spatially
explicit cohort model.

## Files

- `AFRF_DECISION_PACK.md` — AFRF decision context.
- `gavin-mdwr/` — public tactical-operational handoff, schedule, target report
  and KPI files.
- `GAVIN_MDWR_SCENARIO.pdf` — this brief.
- `AFRF_EARLY_MANAGEMENT_PLAN.md` — the Gavin + Knife planning brief.

## Decision boundary

This screen demonstrates the size and direction of the MDWR trade-off under the
official fine-map classes and a corrected 40-year re-entry. It does not approve
an AAC, a group-selection layout, or a legal habitat-class assignment. The next
steps are to reconcile the adjusted Appendix 9 compartment map, review the 2007
legal order and current UWR boundary, and then decide whether the public screen
can become a compliance-grade plan.
