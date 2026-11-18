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

## Habitat-class assumption

The available legacy spatial layer has `WORKING_CI = MDWR`, but it does not
carry the official Appendix 9 High/Moderate/Low habitat-class map. This screen
uses a documented **BEC proxy**:

| Proxy class | BEC | Area | Blocks | Pass intensity |
| --- | --- | ---: | ---: | ---: |
| High | ICHmk3 | 14.27 ha | 19 | 33% |
| Moderate | ICHmk3/SBSdw | 213.06 ha | 136 | 25% |
| Low | SBSdw1 | 2,571.98 ha | 1,288 | 20% |

The proxy is a screening assumption, not a legal habitat-class delineation.

## Method

- Clone the legacy tracks used by MDWR fragments.
- Remove clearcut from the MDWR clones.
- Add Table 30 group-selection treatments at the BEC-proxy pass intensity.
- First entry at age 80; **40-year re-entry** after that.
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
| `gavin-mdwr` group selection | **0** | **3.735M m³** | **124,508 m³** | **80,704 m³** | **201,462 m³** | **395,682 m³** | **10/43/8** |
| MDWR deferral floor | 0 | 3.560M m³ | 118,678 m³ | 64,963 m³ | 151,070 m³ | 1,493,175 m³ | 8/47/6 |

The MDWR-constrained group-selection screen reduces total production by about
**31%** against the timber-only upper bound and does not meet the existing
policy floor. The deferral floor is lower again in timber but leaves much more
standing stock.

The target status is reported against the existing 174k policy target set. It
is a **trade-off result**, not a failure hidden by a redefined target.

## Limits

- The official Appendix 9 habitat-class map is not in the legacy layer; the BEC
  proxy must be replaced before a compliance claim.
- The block-level partial-cut curve is a volume screen. It does not lay out
  spatial groups, enforce the 0.4/0.7 ha group-size cap, or simulate
  within-block cohort structure.
- Preparatory thinning at least ten years before group selection is not
  modelled.
- No public AFRF private finance ledger is used or fabricated.
- The 2007 legal order and current UWR boundary still need review.

## Files

- `AFRF_DECISION_PACK.md` — AFRF decision context.
- `gavin-mdwr/` — public tactical-operational handoff, schedule, target report
  and KPI files.
- `GAVIN_MDWR_SCENARIO.pdf` — this brief.
- `AFRF_EARLY_MANAGEMENT_PLAN.md` — the Gavin + Knife planning brief.

## Decision boundary

This screen demonstrates the size and direction of the MDWR trade-off. It does
not approve an AAC, a group-selection layout, or a legal habitat-class
assignment. The next technical step is to obtain the official Appendix 9
habitat-class map and replace the BEC proxy before using the result in a
management decision.
