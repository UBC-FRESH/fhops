# Gavin Lake MDWR — block vs group decision brief

Status: **decision gate, not a new model result**

Date: 2026-11-20

## Bottom line

The **legal-order block screen is public**. The legal-order group one-cut state
is a diagnostic and does not replace it.

| Result | Harvested volume | Area basis | Status |
|---|---:|---|---|
| Full-estate legal-order block screen | **4.179M m³ / 300 yr** | 5,663.7 ha estate | public policy screen |
| MDWR-only legal-order block screen | **0.619M m³ / 300 yr** | 2,799.3 ha model estate | comparison baseline |
| Legal-order group cohort, regrown phase | **0.679M m³ / 300 yr** | 2,797.5 ha old layout | diagnostic prototype |
| Repaired-layout cohort, not phase | **0.630M m³ / 300 yr** | 27,083 groups / 2,721.8 ha | diagnostic, not a phase result |
| Assigned-openings-only cohort | **0.500M m³ / 300 yr** | 4,671 openings / 1,386.4 ha | diagnostic; 928 openings uncut |

The group/block MDWR ratio is **1.10**. That is a material gap, not a geometry
error: the 0.1 ha minimum opening removes assigned area that the block screen
continues to cut.

## Legal-order basis

The 2007 Transition/Deep Snowpack GAR order sets:

- **45 m²/ha in ICH** and 40 m²/ha elsewhere;
- Low 33%, Moderate 25%, High 20% per pass;
- 120/160/200-year rotations with 3/4/5 patches;
- 0.1–0.4 ha warm openings; other 0.1–0.7 ha in transition and 0.1–1.0 ha
  in deep; frost-prone 0.1–0.3 ha in transition and 0.1–0.4 ha in deep.

The block screen uses these parameters. The group layout uses a 0.7 ha maximum
everywhere and does not yet apply the frost cap; in ICH/deep this is
conservative on size. Earlier MWP Table 30 ordering and 40 m²/ha screens are
superseded.

## Group-state facts

- 25,777 groups on 1,443 blocks;
- 2,797.5 ha represented (old layout);
- 3,954 assigned openings, all **≥0.1 ha**;
- 1,431.9 ha scheduled;
- maximum opening 0.7 ha;
- **291 frost-cap exceedances / 142.2 ha** in the preliminary screen;
- **181 assigned openings not fully inside the UWR** (42.6 ha outside);
- 11,910 accepted cohort entries;
- final standing volume **1,141,775 m³**;
- initial BA **102,863 m²**; final BA **184,534 m²**.

The repaired-layout cohort state has its own diagnostic:

- 27,083 groups in 1,427 blocks;
- 12,534 cut events, 1,684.1 ha cut;
- **629,809 m³** harvested;
- final stock **1,111,922 m³**, final BA **180,249 m²**;
- no regrown phase schedule yet.

This cohort cuts all groups, not only the 4,671 assigned openings. That is an
inherited cohort-model limitation, not a repair result.

## Data-source check

The approved UWR boundary and stand-structure classes were downloaded from the
BC Geographic Warehouse and clipped to Gavin:

- **UWR U-5-002 / dwl_9 Beaver Valley North:** 2,726.4 ha;
- **High 697.9 ha, Moderate 1,013.2 ha, Low 1,015.3 ha.**

The model estate is 2,799.3 ha, so about 71 ha needs reconciliation. The
official class layer is the GWM 7 stand-structure layer, not the adjusted
Appendix 9 compartments.

Frost-prone is defined by the legal order as medium, high or very high summer
frost hazard. The Steen et al. 1990 table and a 5 m DEM are available; a
preliminary screen is reported below.

## Preliminary frost screen

A preliminary screen now applies the FRDA Report 157 Table 3 process to the
existing group layout, using a 5 m DEM and a 500 m topographic position index.
It is a screening diagnostic, not a field-verified legal map.

- 540 assigned openings (186.4 ha) are frost-prone;
- **291 assigned openings (142.2 ha)** exceed the frost opening cap;
- 36 assigned openings (19.1 ha) are warm-aspect cases that exceed the 0.4 ha
  cap;
- 181 assigned openings (42.6 ha outside) are not fully inside the approved
  UWR;
- 499 assigned openings (221.6 ha) fail at least one of the frost/opening-size
  or UWR tests.

The threshold sensitivity run still leaves at least 93.5 ha of assigned
frost-cap exceedances, so this is not a threshold artefact.

### Repaired layout

A clipped-and-capped repair of the existing layout is saved as a diagnostic.
It clips every group to the UWR and splits oversized groups on a 10 m grid:

- 27,110 groups; 2,722.4 ha;
- 4,671 assigned openings; 1,386.4 ha;
- zero cap violations and zero groups outside the UWR;
- assigned area falls by 46.4 ha, mostly because 42.6 ha was outside the UWR.

A cohort state has now been run on the repair: **629,809 m³** harvested,
final stock **1,111,922 m³**, final BA **180,249 m²**. It is not a phase result,
and the public group result below still refers to the old layout. The cohort
script cuts all groups (1,684.1 ha), not only the 4,671 assigned openings
(1,386.4 ha).

An **assigned-openings-only** cohort was also run:

- 4,671 assigned groups in 875 blocks;
- 3,743 groups cut once or more, covering 1,106.79 ha;
- **928 assigned groups (279.64 ha) remain uncut**;
- 4,530 cut events covering 1,350.13 ha of event area;
- **499,597 m³** harvested;
- final state **554,774 m³**, final BA **96,950 m²**.

The 928 uncut groups are the cohorts that have no matching block entry in the
300-year schedule. The cohort script ignores the layout's `entry_offset`, so
this is not yet a complete legal-opening ledger. The 554,774 m³ final state
covers only the 1,386.4 ha assigned area, not the full 2,722.4 ha estate, and
is not comparable to the whole-estate 1,000,000 m³ floor.

## Interim group target diagnostic

There is no approved group target framework. As a diagnostic, the legal-order
block MDWR mean period (20,634 m³) gives an interim even-flow band of 10,317 to
30,951 m³ per period, with a 1,000,000 m³ final-stock floor and 150,000 m²
final-BA floor.

The old group cohort final stock (1,141,775 m³) and final BA (184,534 m²) pass,
but the 40-year schedule period range (4,180–62,626 m³) fails the interim
even-flow band. The repaired-layout cohort is 0.630M m³, but it has no regrown phase result yet.
The assigned-only cohort is 0.500M m³ but leaves 279.6 ha uncut. The 0.679M m³ /
26-of-30 diagnostic below remains the old layout.

A horizon-aware per-block phase schedule was regrown at the shifted ages. It
produces **10,204–30,937 m³** and puts **26 of 30** periods inside the interim
band. The fixed-volume 30/30 result was a scheduling artefact, not a valid
regrown cohort result.

The four late periods are only about 113 m³ below the 10,317 m³ floor. Moving
the floor to 10,200 would be a 1.1% goalpost shift. The options are: keep the
band and fail, approve a wider/asymmetric band, or extend the horizon/treatment
schedule. I recommend keeping the band and the block policy screen until that is
a policy decision.

## Why the block screen stays public

1. The group model is a legal-order cohort prototype. A repaired layout and a
   cohort state now exist, but the regrown phase and target framework are
   missing.
2. The repair removes the 327 assigned opening-size violations and the
   181 outside-UWR openings, but it loses 46.4 ha of assigned area and has not
   been rebalanced to pass targets. The all-group cohort cuts 1,684.1 ha, and
   the assigned-only cohort leaves 928 openings / 279.6 ha uncut because it
   ignores layout entry offsets.
3. The adjusted Appendix 9 compartment map is a scanned plan map, not a GIS
   layer, and has not been reconciled.
4. The UWR boundary and stand-structure classes have been downloaded from BCGW
   and clipped to Gavin (2,726.4 ha). Independent legal review is still needed;
   the repaired layout uses that clip and has no residual outside-UWR groups.
5. The group run has no policy target framework comparable to the block
   screen’s 9/37/15 status.
6. The group result is 1.10× the MDWR block result on harvested volume.

## Replacement gate

The group state can replace the block-level public result only after:

- full UWR-consistent group coverage;
- a modelled frost-compliant layout using the Steen et al. 1990 process;
- a cohort/ledger that cuts every assigned opening at its layout entry offset;
- a regrown phase result on the repaired layout;
- reconciled adjusted Appendix 9 compartments and independent UWR review;
- group target framework;
- a group-state public scenario small enough to use.

## Decision

- Keep `gavin-mdwr` as the public legal-order block screen.
- Keep `gavin-mdwr-group` as a diagnostic prototype.
- Do not present the 0.522M m³ group result as a replacement or compliance
  determination.

## Evidence

- `GAVIN_MDWR_SCENARIO.pdf` — current block/group brief
- `notes/2026-11-19_gavin-mdwr-legal-review.md` — legal and map review
- `planning/2026-11-20_gavin-mdwr_group_matrix_legal.json`
- `planning/2026-11-20_gavin-mdwr_group_layout_legal.json`
