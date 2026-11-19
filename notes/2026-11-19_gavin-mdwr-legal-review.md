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

- **9,491 assigned groups** on **977 blocks**;
- **1,382.7 ha** of assigned group area;
- maximum group area **0.7 ha**; warm groups are capped at 0.4 ha;
- 68 scheduled blocks produced no cell groups because the block is smaller
  than the 10 m cell/edge geometry;
- 6,245 generated groups remain unassigned.

The layout uses cell-center aspect/slope and splits cells into contiguous groups.
It is a **schematic capacity/verification layer**, not an operational group
layout. It does not enforce a minimum group size, model cohort growth, represent
windthrow, or feed group-specific volume back into WS4. The next step is to
replace this cell prototype with a spatially explicit cohort model.
