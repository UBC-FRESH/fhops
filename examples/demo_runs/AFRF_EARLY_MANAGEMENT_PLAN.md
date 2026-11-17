---
title: "AFRF Knife Creek — Early Draft Management Plan and Modelling Brief"
subtitle: "Draft for AFRF leadership and the Dean's Office"
date: "17 November 2026"
---

# AFRF Knife Creek — Early Draft Management Plan and Modelling Brief

**Status:** Draft for discussion. Not an approved management plan, not a legal
compliance determination, and not an audited financial forecast.

**Prepared for:** AFRF leadership and the Dean's Office

**Purpose:** Show the structure of the management plan, the modelling approach,
the scenario plan, and early preview results now, so the faculty can decide
whether to support a focused calibration and review programme before committing
to a full field campaign.

## 1. Executive summary

We have a working, reproducible modelling stack for the AFRF estates:

- a full-estate Gavin Lake policy screen;
- a full-block Knife Creek screening chain;
- a LiDAR-informed Knife Creek spatial-clump screen;
- a separate MKRF full-estate scenario set that exercises the same stack at a
  much larger scale.

The Knife Creek work now has a coherent draft management story:

- 3,481.77 ha of VRI blocks inside the Knife Creek SUP;
- 160 spatial blocks;
- HMZ-restricted silviculture;
- a four-to-eight-entry FVS-BC state-transition library;
- a compiled WS4 dataset with HMZ-specific track offers;
- a 300-year sustained legal-HMZ policy screen;
- a 2024 LiDAR canopy inventory with 278,318 canopy trees, spatial clumps, and
  a first block-level FVS clump screen.

The early numbers are useful for structure and direction:

| Screen | Production | Annual net after cost | NPV 4% | Status |
| --- | ---: | ---: | ---: | --- |
| Gavin policy | 5,385,149 m³ / 300 yr | ~CAD 1.95M/yr | ~CAD 48.3M | decision-grade public policy screen |
| Knife legal-HMZ GWM | 2,433,385 m³ / 300 yr | ~CAD 882k/yr | ~CAD 39.3M | structural policy screen |
| Knife LiDAR-gated GWM | 2,343,814 m³ / 300 yr | ~CAD 850k/yr | ~CAD 38.0M | structural policy screen with a real LiDAR block gate |
| Knife LiDAR spatial-clump FVS | 2,564,179 m³ / 300 yr | ~CAD 930k/yr | ~CAD 55.6M | structural LiDAR pilot, not decision-grade |

The Knife numbers are now plausible enough to support an early draft, but they
are not yet defensible as a final AAC or budget. The main missing ingredient is
not more model plumbing. It is field calibration: measured DBH, species
composition, mortality, damage, and a CFI or released tree list for Knife Creek.

**Decision requested:** endorse this as the draft structure and modelling
framework, and support a focused calibration and technical-review programme.
That programme should be staged: a small, high-value field and LiDAR calibration
campaign first, followed by a decision on a larger field season only if the
early results remain encouraging.

## 2. Why this matters now

The Dean's Office needs to see enough structure and evidence to judge whether
this is a credible path, without waiting for a full field campaign.

This brief is deliberately written to separate:

1. what is already strong enough to support a management-plan structure;
2. what is provisional and should be labelled as such; and
3. what cannot be claimed without field calibration or legal review.

That separation is the difference between a useful early draft and a result that
looks more certain than it is.

## 3. Management context and draft objectives

### 3.1 Resource

- Knife Creek SUP S15382: 3,533.13 ha legal gross boundary.
- Modelled VRI block area: 3,481.77 ha.
- 160 spatial blocks after the VRI/HMZ join.
- BEC: predominantly IDFdk3, with IDFxm at the margins.
- Mule-deer HMZ is a first-order constraint:
  - HMZ 1/3/4 (M): Low or Moderate only;
  - HMZ 2 (L): Low only;
  - HMZ 5 (A): all classes, effectively absent inside the SUP.
- The current work uses the public HMZ layer and the legal matrix as a structural
  constraint. It is not a legal compliance opinion.

### 3.2 Draft management objectives

1. Maintain continuous forest cover and the uneven-aged stand structure required
   by the Knife Creek GWM context.
2. Respect the HMZ offer matrix and retain the 4–10-tree clump and canopy-opening
   structure.
3. Produce a sustainable, defensible harvest level without treating the first
   model result as an approved AAC.
4. Maintain or improve mule-deer winter-range habitat indicators.
5. Provide a transparent, reproducible evidence trail from inventory to
   treatment to schedule to finance.
6. Build a plan that can be recalibrated when CFI and LiDAR calibration data
   arrive, rather than rebuilding the framework.

### 3.3 Draft management plan structure

The early draft should follow this structure:

1. **Purpose, legal context and decision framework**
2. **Resource description and information quality**
3. **Management objectives, constraints and zones**
4. **Silvicultural system and GWM/HMZ rules**
5. **Growth, yield and state-transition model**
6. **Harvest scheduling, AAC and scenario logic**
7. **Access, hauling, landing and operational feasibility**
8. **Habitat, biodiversity and mule-deer monitoring**
9. **Financial analysis and sensitivity**
10. **Adaptive management, review triggers and governance**
11. **Appendices: data provenance, model cards, run register, assumptions**

This is the structure we recommend bringing to the Dean's Office. The current
brief fills in the modelling and early-results sections; the legal and
silvicultural sections still need internal review.

## 4. Modelling approach

### 4.1 Evidence chain

The stack is deliberately traceable:

```text
public inventory / LiDAR / PSP
        ↓
FVS-BC state-transition library
        ↓
canonical state graph + HMZ tracks
        ↓
WS4 compiled spatial dataset
        ↓
FHOPS / WS4 schedule and scenario simulation
        ↓
operational screens, finance envelope, run register
```

The important design choice is that the state-transition library is the bridge.
Every track is tied to an FVS-BC state, a selection regime, a stem list, and a
run record. A track with no provenance is treated as a curve, not evidence.

### 4.2 FVS-BC state library

Current Knife Creek library:

- eight 30-year entries per stand/regime;
- 216 per-chain states;
- 192 transitions;
- 35 canonical states;
- 48 canonical transitions;
- two canonical cycles;
- clump-harvest volume counted in the transition cut.

The clump-volume correction is material. Earlier versions counted only the FVS
selection cut and left post-FVS clump harvest out of the reported yield. That
made a productive cycle look like a zero-yield reserve cycle.

### 4.3 Spatial dataset and HMZ

`ws4/dataset_kc_spatial_v5`:

- 160 blocks;
- 140 tracks: 35 canonical states × 4 HMZ groups;
- 96 treatments;
- HMZ offers enforced through track copies;
- `ws4 validate` passes.

The dataset is a structural fixture, not a KC operating model. Its tree lists
are PSP-derived analogs; its clump reserve is a proxy unless the LiDAR clump
path is used.

### 4.4 LiDAR

The 2024 LidarBC inventory provides:

- 278,318 canopy trees;
- 160/160 blocks with coverage;
- 117,297 trees at least 20 m tall;
- 6,046 four-to-ten-tree clumps at 10 m linkage;
- 88,640 reserve trees and 28,191 harvest trees in the spatial reserve scenario.

The current spatial-clump FVS pilot:

- takes a one-hectare LiDAR sample per block;
- groups trees at least 20 m into 10 m clumps;
- splits clumps into 4–10-tree groups;
- reserves the three largest trees per clump;
- harvests the remaining clump trees;
- treats singletons as reserved;
- uses a stable three-digit FVS plot key so after-treatment rows can be traced
  back to the source clump;
- scales LiDAR TPH to VRI live stems per hectare;
- scales LiDAR DBH so block BA matches VRI BA;
- samples tree-level species from the VRI species composition.

This is a real spatial-clump implementation, but it is still a **structural
pilot**. The LiDAR DBH is height-allometry, the species are sampled from VRI
composition, and the one-hectare sample is scaled to VRI TPH/BA.

### 4.5 Operational and financial layer

FHOPS and WS4 operational screens provide:

- block-level harvest decisions;
- landing and machine constraints;
- haul distance and truck-fleet screens;
- period production and target reports;
- public finance envelopes.

The finance values are an AFRF MWP #3 Figure 7 public envelope. They are not a
budget forecast. NPV uses annual cash flows spread uniformly inside 10-year
periods.

## 5. Scenario plan

The scenario plan is intentionally layered. We do not want one “best” number;
we want a defensible family of screens that shows what changes when an assumption
changes.

### 5.1 AFRF scenarios

| Scenario | Purpose | Current status |
| --- | --- | --- |
| `gavin-policy` | Decision-grade Gavin public policy screen | 61/61 targets met; use as AFRF benchmark |
| `knife-gwm-policy` | Legal-HMZ sustained GWM screen | structural; main Knife policy candidate |
| `knife-gwm-lidar-policy` | Adds a real LiDAR block-level harvest gate | structural; tests LiDAR eligibility |
| `knife-lidar-clump-policy` | Replaces the proxy with spatial LiDAR clumps in FVS | structural pilot; strongest LiDAR test |
| `knife-structural` | Earlier single-cycle comparison | retained for traceability |

### 5.2 MKRF scenarios

The MKRF set is a separate estate and a stress test of the same stack:

| Scenario | Production | Annual net after cost | NPV 4% |
| --- | ---: | ---: | ---: |
| low-44 | 3,170,458 m³ / 100 yr | ~CAD 2.06M/yr | ~CAD 48.3M |
| base-44 | 3,148,735 m³ / 100 yr | ~CAD 2.04M/yr | ~CAD 48.2M |
| high-44 | 2,794,062 m³ / 100 yr | ~CAD 1.81M/yr | ~CAD 42.5M |

MKRF is not the Knife Creek management plan. It is evidence that the modelling
stack and scenario discipline are portable to a much larger estate.

### 5.3 Scenario logic

The plan should carry three Knife Creek cases forward:

1. **Legal-HMZ GWM base case** — the constraint-respecting screen.
2. **LiDAR-informed spatial clump case** — the case that tests whether observed
   clump geometry changes the harvest level.
3. **Stress/sensitivity case** — low/base/high finance, plus a no-harvest or
   reserve-heavy habitat case.

The decision rule should not be “pick the highest NPV.” It should be:

- does the case meet the HMZ constraints?
- is the growth/yield evidence strong enough for the claimed harvest level?
- does the operational screen close?
- does the habitat indicator stay within the intended range?
- can we explain the result without hiding the uncertainty?

## 6. Early preview results

### 6.1 Gavin Lake

- 2,907 blocks / 5,663.66 ha
- 5,385,149 m³ over 300 years
- 61/61 public policy targets met
- annual net after cost ~CAD 1.95M
- NPV 4% ~CAD 48.3M
- P00: 192 blocks, 175,533 m³, 315-day screen
- P01: 237 blocks, 176,512 m³, 355-day screen

### 6.2 Knife Creek legal-HMZ GWM

- 160 blocks / 3,481.77 ha
- 157 blocks scheduled
- 1,570 entries
- 2,433,385 m³ over 300 years
- production positive in all 30 periods
- annual net after cost ~CAD 882k
- NPV 4% ~CAD 39.3M
- P00: 208,452 m³; P29: 29,632 m³

### 6.3 Knife Creek LiDAR spatial clump

- 132 blocks scheduled / 160 mapped
- 624 entries
- 2,564,179 m³ over 300 years
- production positive in all 30 periods
- annual net after cost ~CAD 930k
- NPV 4% ~CAD 55.6M
- P00: 384,283 m³; P29: 83,255 m³

The LiDAR case is not automatically better because its NPV is higher. It
harvests more volume earlier. That is exactly why the scenario must be reviewed
for habitat and legal fit, not selected on NPV alone.

## 7. Confidence ladder

| Area | Current confidence | Why |
| --- | --- | --- |
| Estate boundary and block geometry | High | Public SUP, VRI and HMZ layers are explicit and reproducible |
| HMZ area and offer matrix | Medium-high | Public layer and legal matrix captured; current order still needs review |
| FVS-BC state transitions | Medium | Structural runs exist; PSP analog is not KC-calibrated |
| Clump-harvest accounting | High | Fixed and traceable in the v3 library |
| LiDAR tree positions and clumps | Medium | Real canopy inventory; DBH is allometry and species are VRI-sampled |
| Growth and yield level | Low-medium | No KC CFI; PSP analog; model response uncertain |
| Financial envelope | Low-medium | Public MWP #3 Figure 7 envelope, not a budget |
| Operational feasibility | Medium | Queue/landing/haul screens exist; roads are not surveyed |
| Legal compliance | Not established | Structural HMZ envelope only; no legal opinion |

## 8. What field data buys

A focused calibration programme would change the quality of the plan in four
specific ways:

1. **Measured DBH and BA.** Calibrates the LiDAR height–DBH relation and replaces
   the VRI scaling assumption.
2. **Species composition.** Replaces VRI-sampled species with measured tree-level
   composition.
3. **Mortality, damage and ingrowth.** Makes the state transitions defensible
   instead of structural.
4. **CFI or released tree list.** Anchors the growth and yield model to Knife
   Creek rather than a regional PSP analog.

The field programme does not need to cover the whole estate at once. A
stratified pilot across the main HMZ/BEC/productivity strata would be enough to
test whether the current results are credible. If the pilot shows the model is
tracking, it justifies a larger campaign. If it does not, we learn that early,
before the plan is presented as final.

## 9. Staged workplan

### Next 2–4 weeks

- Internal review of this draft and the scenario logic.
- Choose calibration strata and sample design.
- Validate the LiDAR clump layer against VRI and available PSP plots.
- Fix or explicitly document the small number of blocks that fail the current
  FVS row mapping.
- Produce a legal/HMZ review checklist.

### Next field season

- CFI/PSP remeasurement in the selected strata.
- Measured species, DBH, height, damage and mortality.
- LiDAR plot calibration and, if possible, point-cloud CHM improvement.
- Re-run the FVS-BC library with calibrated tree lists.

### Next 4–6 months

- Rebuild the state library and WS4 dataset.
- Re-run legal-HMZ, LiDAR-gated and spatial-clump scenarios.
- Complete the operational and finance review.
- Produce the first full draft management plan for internal review.

### Decision gate

Do not treat this as an approved AAC or budget. The gate is:

- calibrated growth/yield evidence;
- HMZ/legal review;
- operational feasibility;
- habitat indicators;
- transparent finance envelope.

## 10. What we are asking for

We are asking the Dean's Office to support:

1. **Endorsement of the draft structure and scenario framework** as the basis for
   consultation, not as an approved plan.
2. **A focused calibration and technical-review programme** — field pilot,
   LiDAR calibration, legal/HMZ review, and model review.
3. **A staged resource decision** — small calibration first, larger field
   campaign only if the early results remain credible.

The current work is strong enough to show the structure, the modelling approach,
the scenario plan and preliminary results. It is not strong enough to defend a
final AAC, a final revenue forecast, or a legal compliance claim. That is the
honest boundary, and it is the right basis for a Dean's Office conversation.

## Appendix A — Run register

| Run | Role |
| --- | --- |
| `gavin-policy` | Gavin decision-grade public policy screen |
| `knife-gwm-policy` | Legal-HMZ sustained GWM screen |
| `knife-gwm-lidar-policy` | LiDAR block-gate screen |
| `knife-lidar-clump-policy` | LiDAR spatial-clump FVS pilot |
| `knife-structural` | Earlier structural comparison |
| `mkrf-low-estate` | MKRF low-44 full-estate screen |
| `mkrf-full-estate` | MKRF base-44 full-estate screen |
| `mkrf-high-estate` | MKRF high-44 full-estate screen |

## Appendix B — Evidence paths

```text
fhops-public-demo/examples/demo_runs/
fhops-public-demo/examples/demo_runs/AFRF_DECISION_PACK.md
fhops-public-demo/examples/demo_runs/MKRF_DECISION_PACK.md
fhops-public-demo/examples/demo_runs/MKRF_SCENARIO_COMPARISON.md
femic-afrf-knifecreek-instance/ws4/state_library_v3/
femic-afrf-knifecreek-instance/ws4/dataset_kc_spatial_v5/
femic-afrf-knifecreek-instance/data/lidar/kc_2024/
femic-afrf-knifecreek-instance/notes/reference/lidarbc-kc-pilot.md
```

## Appendix C — What not to say

Do not say:

- “This is the approved AAC.”
- “This is a budget forecast.”
- “This proves legal compliance with the GWM order.”
- “The LiDAR inventory is a CFI.”
- “The Knife Creek results are calibrated.”

Say instead:

- “This is a reproducible early-draft policy screen.”
- “The legal-HMZ case and the LiDAR spatial-clump case bracket the current
  modelling range.”
- “The remaining uncertainty is field calibration and legal review, not a
  missing modelling framework.”
