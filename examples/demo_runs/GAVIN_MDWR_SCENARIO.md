# Gavin Lake — Beaver Valley MDWR legal-order screens

Status: **legal-order parameter screens, not approved plans or compliance
determinations**

## Current public results

| Result | Volume | Targets |
|---|---:|---:|
| Full-estate block screen | **4.179M m³ / 300 years** | **9/37/15** |
| MDWR-only block screen | **0.619M m³** | not comparable |
| Legal-order group cohort, regrown phase | **0.679M m³** | no target framework |

The block screen is the public policy result. The group screen is a spatial
diagnostic and does not replace it.

## Legal order

The 2007 Transition and Deep Snowpack GAR order sets:

- group-selection basal area: **45 m²/ha in ICH**, 40 m²/ha elsewhere;
- Low: **33% per pass**, 120-year rotation, 3 patches;
- Moderate: 25%, 160-year rotation, 4 patches;
- High: **20% per pass**, 200-year rotation, 5 patches;
- openings: **0.1–0.4 ha** warm aspect; **0.1–0.7 ha** other in transition and
  **0.1–1.0 ha** in deep; **0.1–0.3 ha** frost-prone in transition and
  **0.1–0.4 ha** in deep.

These differ from the MWP #3 Table 30 ordering used by earlier versions of this
screen. The current public block and legal group screens use the GAR order.

## Block result

| Metric | Value |
|---|---:|
| Production | **4.179M m³** |
| Mean period | 139,312 m³ |
| Min period | 93,479 m³ |
| Max period | 221,223 m³ |
| Period-30 stock | 1,493,175 m³ |
| Targets | **9/37/15** |
| MDWR clearcuts | 0 |

The block screen remains a full-area partial-cut volume screen. It carries the
legal class fractions and 45/40 BA gate, but it is not a spatial group layout or
a compliance determination.

## Group result

The legal-order group layout:

- 25,777 groups on the MDWR;
- 2,797.5 ha represented (old layout);
- 3,954 assigned openings, all **≥0.1 ha**;
- 1,431.9 ha scheduled;
- maximum opening 0.7 ha;
- **291 frost-cap exceedances / 142.2 ha** in the preliminary screen;
- **181 assigned openings not fully inside the UWR** (42.6 ha outside);
- 11,910 accepted cohort entries.

| Metric | Value |
|---|---:|
| Harvested volume | **0.679M m³** |
| Mean period | 21,004 m³ |
| Min period | 10,204 m³ |
| Max period | 30,937 m³ |
| Final standing volume | **1,141,775 m³** |
| Initial BA | 102,863 m² |
| Final BA | 184,534 m² |

A preliminary frost screen now applies the FRDA Report 157 Table 3 process
using a 5 m DEM and a 500 m topographic position index. It is a screening
diagnostic, not a field-verified legal map.

- 540 assigned openings (186.4 ha) are frost-prone;
- **291 assigned openings (142.2 ha)** exceed the frost opening cap;
- 36 assigned openings (19.1 ha) exceed the 0.4 ha warm-aspect cap;
- 499 assigned openings (221.6 ha) fail a frost/opening-size or UWR test.

The threshold sensitivity run still leaves at least 93.5 ha of frost-cap
exceedances.

A clipped-and-capped **layout repair** is now saved as a diagnostic:

- 27,110 groups; 2,722.4 ha;
- 4,671 assigned openings; 1,386.4 ha;
- zero cap violations and zero groups outside the UWR;
- assigned area falls by 46.4 ha, mostly because 42.6 ha was outside the UWR.

A cohort state has now been run on the repair:

| Metric | Repaired cohort |
|---|---:|
| Groups in state | 27,083 |
| Blocks | 1,427 |
| Cut events | 12,534 |
| Cut area | 1,684.1 ha |
| Harvested volume | **0.630M m³** |
| Final standing volume | **1,111,922 m³** |
| Final BA | 180,249 m² |
| BA-gate failures | 0 |

This is a cohort state, not the regrown phase result. The cohort script cuts all
groups, not only the 4,671 assigned openings (1,386.4 ha); that is an inherited
model limitation.

An **assigned-openings-only** cohort was also run:

| Metric | Assigned-only cohort |
|---|---:|
| Assigned groups | 4,671 |
| Cut groups | 3,743 |
| Uncut assigned groups | **928 (279.64 ha)** |
| Cut events | 4,530 |
| Event area | 1,350.13 ha |
| Harvested volume | **0.500M m³** |
| Final state | 554,774 m³ |
| Final BA | 96,950 m² |

The 928 uncut groups are cohorts with no matching block entry in the 300-year
schedule; the cohort script ignores layout `entry_offset`. The final state is
for the 1,386.4 ha assigned area, not the full estate, so it is not comparable
to the whole-estate 1,000,000 m³ floor.

An **entry-offset ledger** cuts all 4,671 assigned openings exactly once:

| Metric | Entry-offset ledger |
|---|---:|
| Assigned openings | 4,671 |
| Blocks | 875 |
| Cut area | **1,386.43 ha** |
| Harvested volume | **504,601 m³** |
| Uncut assigned openings | **0** |
| First-decade volume | 148,505 m³ |
| Mean cut BA | 82.2 m²/ha |

This is a one-cut ledger, not a phase or final-stock result. The phase optimizer
was run on it:

| Metric | Entry-offset phase |
|---|---:|
| Total volume | **579,763 m³** |
| Mean period | 19,325 m³ |
| Maximum period | 30,950 m³ |
| Minimum period | **3,474 m³** |
| Periods in band | **26/30** |

The four late periods are **6,603 / 3,944 / 3,841 / 3,474 m³**. There are no
ceiling violations. The 119-year phase cap and the early concentration of
assigned entries leave too small a late-entry pool to fill the tail. This is a
structural limit of the one-cut 300-year ledger, not a local optimizer failure.

The 0.679M m³ / 26-of-30 result in the table above still refers to the old
layout; the group/block MDWR ratio is about 1.10.

## Limits

- The adjusted Appendix 9 compartment map has not been reconciled with the
  fine BC long-term objective polygons.
- The UWR boundary and stand-structure classes were downloaded from BCGW and
  clipped to Gavin (2,726.4 ha), but independent legal review is still needed.
  The old group estate is 2,797.5 ha, and 181 assigned openings have
  42.6 ha outside the authoritative clip, so the boundary/layout difference
  must be reconciled.
- The frost screen is preliminary: it uses a TPI proxy, not the field
  air-photo procedure, and no field verification or legal determination.
- The clipped/capped layout is a repair of the old schematic layout, not a
  fresh design. Its pass fractions were not rebalanced; an all-group and an
  assigned-only cohort have been run, but no regrown phase result exists.
- The assigned-only cohort leaves 928 openings (279.64 ha) uncut because it
  ignores layout entry offsets and some cohorts have no block entry.
- The entry-offset ledger cuts all assigned openings once but has no re-entry
  or final stock. Its phase result is 26/30 with a 3,474 m³ tail minimum; the
  phase cap cannot fill the last four periods.
- The block screen does not lay out spatial groups.
- The group screen does not model cohort regeneration, windthrow, or a
  plantation-specific BA model.
- No public AFRF private finance ledger is used or fabricated.

## Public files

- `gavin-mdwr/` — legal-order block handoff.
- `gavin-mdwr-group/` — legal-order group one-cut prototype.
- `GAVIN_MDWR_DECISION.pdf` — block vs group decision brief.
- This brief: `GAVIN_MDWR_SCENARIO.pdf`.

## Decision boundary

The block screen remains public. The group screen is a diagnostic. Replacing the
block screen requires a reconciled Appendix 9 compartment map, an independent
UWR review, a frost-compliant entry-offset ledger, an entry-offset phase that
meets the band, and a comparable target framework.
