> Public project-note copy. See the matching instance planning note.

# Gavin Lake MDWR legal and habitat-map review

Date: 2026-11-19

Status: **review complete; the screen is not a compliance determination**

## Sources reviewed

- 2007 AFRF *Management and Working Plan #3*, section 7.4.2 and Table 30:
  `https://afrf-forestry.sites.olt.ubc.ca/files/2012/03/MWP3WebQuality.pdf`
- 2007 AFRF *Forest Stewardship Plan*, Forest Development Unit strategies and
  Table 7:
  `https://afrf-forestry.sites.olt.ubc.ca/files/2012/03/FSP2007Submitted.pdf`
- BC Ministry of Environment, *Long-Term Habitat Objectives: Beaver Valley
  North (Prouton Lakes)*, 6 December 2001:
  `https://www.env.gov.bc.ca/cariboo/env_stewardship/ecosystems/mdwr_strat/maps/beavervly_lto.pdf`
- BC Cariboo-Chilcotin MDWR Strategy, Information Note #3, *Basal Area
  Requirements for Initiating Group Selection Harvest in Transition and Deep
  Snowpack Zones*, 23 June 2017:
  `https://gov.bc.ca/assets/gov/farming-natural-resources-and-industry/natural-resource-use/land-water-use/crown-land/land-use-plans-and-objectives/cariboo-region/cariboochilcotin-rlup/mdwr_information_note_3.pdf`

## Legal/management findings

### Appendix 9 is a compartment map

MWP #3 says the High/Moderate/Low habitat classes were adjusted to coincide
with the total-chance harvest blocks and are **depicted in Appendix 9**. The
Appendix 9 page is a compartment-level map (BV01–BV09 plus other working
circles), not a block-level GIS layer. It is a raster image in the public MWP.

The available legacy spatial package has `WORKING_CI = MDWR` but no compartment
boundary or habitat-class attribute. The public BC long-term objective map is a
finer polygon layer; it is the source used for the current screen, but it is
**not** the adjusted Appendix 9 compartment boundary.

### Table 30

| Habitat class | Harvest per pass | Cutting cycle | Cohorts | Oldest-cohort maximum age |
| --- | ---: | ---: | ---: | ---: |
| High | 33% | 40 years | 3 | 120 years |
| Moderate | 25% | 40 years | 4 | 160 years |
| Low | 20% | 40 years | 5 | 200 years |

MWP #3 also states:

- maximum group size **0.4 ha on warm aspects** and **0.7 ha on other aspects**;
- preparatory thinning normally precedes group selection by at least ten years;
- group selection is the dominant system in the Beaver Valley MDWR.

### FSP Table 7 qualifies the “no clearcut” assumption

The 2007 FSP Table 7 assigns:

- slightly dry and drier BV MDWR sites to uneven-aged systems including group
  selection;
- fresh and wetter BV MDWR sites to even-aged systems including clearcutting,
  clearcutting with reserves, and irregular shelterwood.

The current public screen applies **no clearcut across the entire MDWR**. That
is a **stricter policy choice** than the FSP text, not a direct transcription of
the FSP. This should be stated explicitly if the screen is used in a policy
discussion.

### GWM 6 basal-area prerequisite

BC MDWR Information Note #3 quotes General Wildlife Measure 6 from the 2007
Transition and Deep Snowpack Mule Deer Winter Range GAR Order: group selection
in the transition/deep snowpack zones requires a **pre-harvest stand basal area
of at least 40 m²/ha** (higher is better) before initiation. The current
full-area screen does not test that prerequisite. The exact GAR order text was
not independently retrieved; the requirement is taken from the BC information
note.

## Model status against the review

| Requirement | Current screen |
| --- | --- |
| No clearcut in MDWR | enforced, but stricter than FSP Table 7 for fresh/wetter sites |
| Table 30 pass intensity | enforced by class |
| 40-year re-entry | modelled with age-preserving passes |
| Class assignment | official fine map, not adjusted Appendix 9 compartments |
| 0.4/0.7 ha group-size cap | not modelled |
| 3–5 cohort structure | not modelled |
| Preparatory thinning | not modelled |
| 40 m²/ha pre-harvest BA | not enforced |
| Legal order/UWR boundary | not independently reviewed |

The current screen remains a **full-area partial-cut volume screen**. It is not
a spatial group-selection layout and cannot demonstrate compliance with the
group-size, cohort, or basal-area requirements.

## What was decided

- Keep the official fine-map classes for the current screen, clearly labelled.
- Do not call the screen an adjusted Appendix 9 implementation.
- Do not claim compliance with the 2007 GAR order until the 40 m²/ha
  prerequisite, group-size cap, and legal boundary are tested.
- Use the corrected age-preserving 40-year re-entry result, not the prior
  first-entry BEC result.
- Retain the no-clearcut policy choice, but disclose that it is stricter than
  FSP Table 7.

## Next technical steps

1. Obtain or digitize the Appendix 9 compartment boundaries and reconcile the
   fine-map classes against the adjusted compartment classes.
2. Add a **40 m²/ha pre-harvest BA** gate to group-selection eligibility.
3. Add a spatial group layout with 0.4 ha warm-aspect and 0.7 ha other-aspect
   caps, plus the 3–5 cohort structure.
4. Review the 2007 GAR order and current UWR boundary independently.
5. Re-run the 300-year screen after those constraints and publish only the
   compliance-grade result.

## Current-BA 40 m²/ha gate

A VRI 2025 basal-area screen was added as a separate sensitivity. Area-weighted
`BASAL_AREA` was intersected with the 1,443 legacy MDWR blocks; blocks with less
than 50% VRI coverage are `unknown` and are held.

| Status | Blocks | Area |
| --- | ---: | ---: |
| Pass, current BA ≥ 40 m²/ha | 625 | 1,296.8 ha |
| Hold, current BA < 40 m²/ha | 789 | 1,429.9 ha |
| Unknown coverage | 29 | 72.6 ha |

The BA-gated official schedule produces **4.592M m³ / 300 years**, mean 153,075
m³ per period, min 79,713 m³, max 269,628 m³, and target status **14 met / 35
below / 12 above**.

This is a **current-snapshot** gate only. It does not model future growth or the
post-pass basal-area recovery needed to clear 40 m²/ha before the next entry.
It is a useful screening sensitivity, not a compliance test.

## Temporal BA ledger

A temporal ledger was added on top of the current-BA snapshot:

- initialize BA from the VRI 2025 block value;
- grow it between entries with the block's WS4 total-volume curve;
- test BA at each candidate entry;
- defer below-threshold entries one year at a time;
- after an accepted pass, deduct the Table 30 pass fraction;
- continue at 40-year intervals.

The temporal gate accepts **1,046 blocks / 2,242.9 ha** and holds **397 blocks /
556.4 ha**. It produces **4.149M m³ / 300 years**, mean 138,297 m³, min 91,965
m³, max 224,726 m³, and target status **10 met / 39 below / 12 above**.

The BA growth is a volume-ratio proxy, not a validated basal-area model. The
group-size cap, cohort structure, preparatory thinning, adjusted Appendix 9
boundaries, and GAR/UWR review remain outstanding.

## Temporal stagger test

A deterministic 0–9 year first-entry stagger by block id improves the temporal
BA-gated screen from 10/39/12 to **13/37/11** targets:

- accepted: 1,045 blocks / 2,238.5 ha;
- held: 398 blocks / 560.8 ha;
- production: 4.154M m³ / 300 years;
- period mean 138,466 m³, min 92,765 m³, max 219,971 m³.

This is still a screening test, not an optimized schedule and not a legal
compliance result. The 0.4/0.7 ha group-size caps, cohort structure, preparatory
thinning, adjusted Appendix 9 boundaries, and GAR/UWR review remain open.

## Group-size capacity check

A terrain capacity screen was run on the staggered temporal schedule. Warm
aspects were classified as slope > 10% and aspect 135–270° (LMH 59); the group
caps are 0.4 ha warm and 0.7 ha other.

- 2,897 accepted entries on 1,045 blocks;
- 1,494.0 ha scheduled cut area;
- 1,121.8 ha warm terrain and 1,432.0 ha other terrain;
- mean minimum group count 2.39, maximum 18;
- 276 blocks have no warm-aspect area;
- 131 blocks have less than 50% valid terrain coverage because of DEM/block
  edges.

This is a **capacity check only**. It does not draw the 0.4/0.7 ha group
polygons, enforce a minimum group size, or model cohort growth. A spatial group
layout is still required before the group-size constraint can be claimed as
implemented.

## Schematic group layout

A 10 m grid-cell prototype was built for the staggered temporal schedule:

- **9,674 assigned groups** on **1,045 blocks**;
- **1,430.3 ha** of assigned group area;
- maximum group area **0.7 ha**; warm groups are capped at 0.4 ha;
- fallback groups now cover the previously missing scheduled blocks;
- 6,409 generated groups remain unassigned.

The layout uses cell-center aspect/slope and splits cells into contiguous groups.
It is a **schematic capacity/verification layer**, not an operational group
layout. It does not enforce a minimum group size, model cohort growth, represent
windthrow, or feed group-specific volume back into WS4. The next step is to
replace this cell prototype with a spatially explicit cohort model.

## Cohort prototype

The assigned groups were partitioned into High 3 / Moderate 4 / Low 5 cohorts,
with 40-year cohort starts and a 120/160/200-year return cycle. Each group uses
the block's WS4 total-volume curve at its initial age and after regeneration;
group BA is allocated proportionally.

The prototype covers 9,674 groups on 1,045 blocks and produces **1.011M m³** over
300 years, with 18,527 cut events and a mean 33,698 m³ per 10-year period. All
1,045 blocks use a base CC successor curve after regeneration where available. It
is not comparable to the 4.154M m³ block-level temporal screen: the group layout
covers 1,430.3 ha rather than the full MDWR, and the regeneration curve is still
a base-matrix approximation rather than a calibrated group-level plantation
model.

This is a cohort-layout prototype, not an operational or legal growth model.
Windthrow, minimum group size, group-specific species/age, and a separate
regeneration curve are still missing.

## Group-level WS4 matrix run

The 9,674 groups were written into a WS4 group matrix: one block/fragment per
group, base AU track, source ages, and a schedule of group cuts. High groups are
cut on a 120-year cycle, Moderate on 160, Low on 200.

The group-level WS4 run produces **1.011M m³ over 300 years**, with **18,527 cut
events**, and **1,430.3 ha** of scheduled group area. This matches the standalone
cohort prototype and confirms that group volume is now flowing through a WS4
matrix state rather than only a spreadsheet.

The group matrix still has no BA account. BA remains a separate screening ledger
derived from the VRI block BA and the group volume ratio. A calibrated
plantation curve, group-specific BA, windthrow, and minimum group size remain
outstanding.

## Group BA account

A group-specific BA account was added to the WS4 group matrix. Each group gets
an initial track and a plantation successor track, with:

- `feature.yield.managed.total`;
- `feature.ba.managed.total`.

The BA curve is fitted to VRI 2025 by BEC as
`BA = b*volume + c*(1-exp(-age/tau))` (R² 0.745/0.888/0.863 for
ICHmk3/SBSdw1/SBSmh), then scaled to each block's initial VRI BA. The group WS4
run produces:

- 9,674 groups / 1,045 blocks;
- 18,527 group cuts;
- **1.011M m³** volume;
- initial BA **57,337 m²**;
- final BA **54,404 m²**;
- final standing yield **190,348 m³**.

BA is now carried as a WS4 account and uses the VRI-fitted BA-volume-age
relationship. It is still a screening calibration, not a plantation BA model.
A calibrated plantation volume curve and group-specific BA dynamics are still
required.

## Complete group state

The group matrix now includes every generated group, including standing groups
that are not assigned to a cut:

- **34,512 groups** on **1,443 source blocks**;
- **2,797.5 ha** total group area;
- **9,674 assigned groups / 1,430.3 ha**;
- **24,838 standing groups**;
- **9,674 cuts** (one accepted entry per assigned group).

The full-state WS4 run produces **0.533M m³** harvested volume, final standing
yield **1,274,641 m³**, initial BA **102,863 m²**, and final BA **255,737 m²**.
The harvested volume is now embedded in a complete group state rather than a
cut-only subset.

This remains a schematic group model: the 2,586.8 ha group state is less than
the 2,799 ha MDWR because of cell/edge coverage, and the BA curve is a VRI
empirical fit rather than a plantation model.

## MDWR-only comparison and area gap

The block matrix was restricted to the 1,443 MDWR blocks and run with the same
temporal schedule. It produces **0.594M m³ / 300 years**, versus **0.533M m³**
for the aligned group state. The group/block ratio is **0.90**; per hectare,
206 m³/ha for the group state versus 212 m³/ha for the block screen. The
remaining difference is the 2,586.8 ha group-area coverage and full-group versus
block-fraction accounting.

The consolidated group state covers **2,797.5 ha** of the **2,799.3 ha** MDWR.
The remaining **1.8 ha** gap is spread across 22 blocks (maximum 0.02 ha in one
block) and is polygon-edge residue.

The aligned group result is close enough to the block screen to compare, but it
remains a spatial prototype; it does not replace the block-level policy screen. The public group scenario currently exposes the 2,586.8 ha cut/standing subset; the full 2,797.0 ha state is in the instance matrix.

## Corrected cohort state

The first cohort implementation applied the 40 m²/ha threshold to every small
group. That was a misapplication: GWM 6 is a **stand-level** prerequisite, not
a per-group gate. The corrected state inherits the accepted block-level BA gate
and uses group BA only as a reported account.

- 34,512 groups on 1,443 blocks;
- 19,587 accepted cohort entries;
- **0.651M m³** harvested;
- final standing volume **1.168M m³**;
- final BA **190,708 m²**;
- group/block MDWR ratio **1.10**; per-hectare 233 versus 212 m³/ha.

This is the cohort-state comparison. It remains a prototype; it does not replace
the block policy screen, and it does not prove the group model is correct.

## GAR order conflict

The exact 2007 Transition and Deep Snowpack GAR order was reviewed on
2026-11-20 (`Amendment_TransDeep_Feb07_ord.pdf`). It establishes:

- GWM 6: ≥45 m²/ha in ICH and ≥40 m²/ha elsewhere for group-selection initiation;
- Table 2: Low 33% / 120-year rotation / 3 patches; Moderate 25% / 160 / 4;
  High 20% / 200 / 5;
- GWM 10 / Table 3: 0.1–0.4 ha warm-aspect openings, 0.1–0.7 ha other, and
  0.1–0.3 ha on frost-prone sites.

The current screen uses the MWP #3 Table 30 mapping (High 33 / Moderate 25 /
Low 20) and a 40 m²/ha gate everywhere. It is **not a legal-order
implementation** and must be rebuilt before a compliance claim.

## Legal-order sensitivity and minimum opening

A legal-order block sensitivity was run with 45/40 m²/ha and Low 33 /
Moderate 25 / High 20:

- full estate: 4.179M m³, targets 9/37/15;
- MDWR-only: 0.619M m³.

The group model cannot yet be called legal: 6,257 of 9,674 assigned groups are
smaller than the 0.1 ha minimum opening, covering 133.1 ha. A minimum-opening
group rebuild is required before the group cohort can be compared on the legal
order.

## Legal-order group rebuild

A legal-order group layout was built with Low 33 / Moderate 25 / High 20 and
the 45/40 BA gate. A small-group merge pulled assigned groups toward the 0.1 ha
minimum.

- 25,222 groups / 2,797.5 ha;
- 4,390 assigned groups / 1,451.8 ha;
- legal group one-cut result **0.530M m³**;
- final standing yield **1,290,057 m³**;
- final BA **256,412 m²**;
- **436 assigned groups / 19.9 ha remain below 0.1 ha**.

The group layout is therefore still not a legal-order implementation. The
remaining sub-0.1 ha groups are isolated edge/fragment cases that cannot be
merged without exceeding the 0.4/0.7 ha caps.
