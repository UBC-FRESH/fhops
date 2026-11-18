---
title: "MKRF Malcolm Knapp Research Forest — Early Draft Management Plan and Modelling Brief"
subtitle: "Draft for UBC Research Forests leadership and the Dean's Office"
date: "17 November 2026"
---

# MKRF Malcolm Knapp Research Forest — Early Draft Management Plan and Modelling Brief

**Status:** Draft for discussion. Not an approved management plan, legal
determination, or audited financial forecast.

**Prepared for:** UBC Research Forests leadership and the Dean's Office

**Purpose:** Provide a management-plan structure, modelling approach, scenario
plan, and early preview results for Malcolm Knapp Research Forest (MKRF). This
is the companion to the AFRF brief for Gavin Lake and Knife Creek.

## 1. Executive summary

MKRF is the largest and most mature model instance in the current WS4/FHOPS
stack:

- 1,763 blocks;
- 4,810.85 ha;
- a 100-year planning horizon in ten 10-year periods;
- three full-estate scenarios (`base-44`, `low-44`, `high-44`);
- public net-revenue and harvest-cost accounts;
- P00/P01 operational handoffs;
- actual 30-day FHOPS Phase I/II haul samples and a rolling full-year Phase I
  aggregate.

The recommended public screen is **`scenario-low-44`**:

| Metric | Low-44 |
| --- | ---: |
| Production | 3,170,458 m³ / 100 years |
| Net after harvest cost | CAD 205.9M |
| Annualized net after cost | CAD 2.06M/yr |
| NPV 2% | CAD 87.3M |
| NPV 4% | CAD 48.3M |
| NPV 6% | CAD 31.9M |
| Targets met / below / above | 33 / 3 / 1 |

The base and high screens are close enough to support a real scenario
conversation:

| Scenario | Production | Annual net after cost | NPV 4% | Targets |
| --- | ---: | ---: | ---: | ---: |
| base-44 | 3,148,735 m³ | CAD 2.04M/yr | CAD 48.2M | 29 / 7 / 1 |
| low-44 | 3,170,458 m³ | CAD 2.06M/yr | CAD 48.3M | 33 / 3 / 1 |
| high-44 | 2,794,062 m³ | CAD 1.81M/yr | CAD 42.5M | 32 / 3 / 2 |

### Retention-value caveat

The low/base/high variants are **area-retention** model rebuilds. WS4 moves a
fraction of eligible fragment area to an unmanaged state; it does not select
species, DBH, or the largest Douglas-fir stems. The current numbers therefore
carry an average area slice, not the high-graded residual cohort described in
the field.

A retention-value audit is in `MKRF_RETENTION_AUDIT.md`. The audit uses the
pinned MKRF 684 tree list to show that the largest 5% of stems contain about
33% of gross value.

I also rebuilt the **no-retention** matrix and repaired its product curve table
against the canonical matrix. The no-retention baseline is now:

- gross log value: **CAD 716.7M**
- production: **3.38M m³**
- net after all cost: **CAD 403.7M**
- gross NPV 4%: **CAD 182.6M**
- net NPV 4%: **CAD 100.9M**

I then built residual-product matrices and re-ran the same target search for
the three residual cases. The product ledgers carry the largest-DF
value/volume reduction, but that product screen still harvests the full area.

I also built a **state-aware value-equivalent residual-area variant**. Each
no-retention block is split into a harvested track and a residual track; the
residual track carries copied feature curves, ages through the horizon and is
not re-entered in this screen. The harvested net/cost curves include a
fixed-cost correction, so the state totals reconcile with the product-ledger
screen. Residual areas are 1,567 ha (low), 2,055 ha (base) and 2,652 ha
(high). The low state run resolves one additional feature-yield target
(32/4/1 instead of 31/5/1); base and high are unchanged.

| Scenario | Gross | Production | Net after all cost | Net after harvest cost | Net NPV 4% | Targets |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| no-retention | CAD 716.7M | 3.38M m³ | CAD 403.7M | CAD 217.8M | CAD 100.9M | 31/5/1 |
| low-44-dfret | CAD 482.1M | 2.27M m³ | CAD 230.1M | CAD 105.2M | CAD 59.3M | 31/5/1 |
| base-44-dfret | CAD 421.6M | 1.99M m³ | CAD 181.4M | CAD 72.1M | CAD 45.2M | 21/15/1 |
| high-44-dfret | CAD 324.8M | 1.54M m³ | CAD 111.8M | CAD 27.3M | CAD 27.6M | 21/15/1 |

Neither screen is yet a species/DBH tree-level largest-DF stem prescription.
The state-aware variant carries a **value-equivalent residual area**, not a
measured stem footprint; the residual track has no scheduled re-entry; and the
species/DBH profile still comes from the pinned MKRF 684 tree list rather than a
full-estate tree list.

Implementation detail is in `MKRF_DFRET_REOPTIMIZED.md` (product-ledger screen)
and `MKRF_DFRET_STATE_AWARE.md` (state-aware area proxy).

**Decision requested:** endorse this as the draft structure for MKRF, and
support the same staged modelling and review path proposed for AFRF. The current
numbers are strong enough for scenario direction, not for a final AAC or budget.

## 2. Management context

MKRF is a separate UBC Research Forest instance, not an AFRF block. It is the
flagship test of the WS4 runtime because it has:

- a large block count and a real spatial topology;
- mature WS4 probability/account surfaces;
- public cost and price bases;
- an operational FHOPS handoff;
- a scenario set that can be compared on production, targets and NPV.

The management-plan structure should preserve the research forest's multiple
mandates: research and teaching, timber production, ecological values,
recreation, and transparent public reporting.

The current model does **not** yet carry every non-timber constraint that a
final MKRF plan will need. The scenario set is therefore a timber-and-finance
screening surface, not a complete land-use plan.

## 3. Draft management-plan structure

1. **Purpose, tenure and research mandate**
2. **Resource description and information quality**
3. **Management goals, objectives and zones**
4. **Silvicultural systems and treatment eligibility**
5. **Growth, yield and WS4 model description**
6. **Harvest scheduling, AAC and scenario logic**
7. **Access, hauling, landings and operational feasibility**
8. **Ecological, wildlife and old-forest constraints**
9. **Financial analysis and sensitivity**
10. **Monitoring, adaptive management and review triggers**
11. **Appendices: data provenance, model cards, run register and assumptions**

## 4. Modelling approach

The MKRF evidence chain is:

```text
FEMIC rebuild / public inventory
        ↓
WS4 compiled matrix (tracks, curves, products, accounts)
        ↓
targets, patch accounts, topology and route configuration
        ↓
WS4 scenario search and simulation
        ↓
FHOPS tactical / operational / hauling handoffs
        ↓
public KPI and finance screens
```

The `ws4/runtime/matrix_silv` dataset is the main runtime surface. The scenarios
are not just alternate maps: they carry different schedules and target
responses, and the public console exposes their production, accounts, targets,
patch metrics, and operational handoffs.

### 4.1 Scenario construction

- Ten 10-year periods, 100-year horizon.
- `base-44`, `low-44`, and `high-44` from the WS4 scenario family.
- Public net-revenue and harvest-cost accounts.
- Patch-size metrics and opening-size policy included in reports.
- P00/P01 operational handoffs with zero remaining work.
- Actual 30-day Phase I/II hauling samples and a rolling full-year Phase I
  aggregate.

The scenario comparison is intentionally a **family**, not a single optimum. A
low, base and high case shows the decision space and the sensitivity of the
target response.

## 5. Early results

### 5.1 Full estate

| Scenario | Blocks | Production | Net after cost | Annualized | NPV 4% |
| --- | ---: | ---: | ---: | ---: | ---: |
| base-44 | 1,221 | 3,148,735 m³ | CAD 203.6M | CAD 2.04M/yr | CAD 48.2M |
| low-44 | 1,212 | 3,170,458 m³ | CAD 205.9M | CAD 2.06M/yr | CAD 48.3M |
| high-44 | 1,211 | 2,794,062 m³ | CAD 180.8M | CAD 1.81M/yr | CAD 42.5M |

Targets are not perfect in any scenario. Low-44 is the strongest public screen at
33 met, 3 below, 1 above. Base-44 is 29/7/1. High-44 is 32/3/2.

### 5.2 Operational evidence

| Scenario | P00 blocks | P00 volume | Makespan | Remaining | Vancouver trucks |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 115 | 390,965 m³ | 329 days | 0 | 12 |
| low | 86 | 367,238 m³ | 296 days | 0 | 12 |
| high | 78 | 299,973 m³ | 247 days | 0 | 10 |

P01 low and high are also complete:

- low P01: 110 blocks, 303,770 m³, 269 days;
- high P01: 112 blocks, 308,550 m³, 264 days.

The 30-day low-44 haul sample delivers 49,934 m³, 1,110 truckloads, and 37
day-1 loads with 12 trucks. The rolling full-year Phase I aggregate is 303,765.7
m³ and 8,295 truckloads across 12 monthly windows, plus 12 monthly Phase II
day-1 samples (282 loads). This is not a continuous 365-day MILP.

## 6. Scenario plan for review

The recommended review set is:

1. **low-44** — primary public screen, best target performance.
2. **base-44** — central comparison against the original scenario family.
3. **high-44** — stress case for reduced production and lower NPV.
4. **low P00/P01 operations** — first two decades of implementation.
5. **30-day and rolling full-year haul** — fleet and delivery screening.
6. **A future ecological constraint case** — not yet built; should add old
   forest, riparian, visual and wildlife constraints before the plan is treated
   as complete.

The choice rule should not be “highest NPV.” It should be:

- does the scenario meet the planning targets or explain the misses?
- does the operational screen close?
- is the opening/patch pattern acceptable?
- are the non-timber values represented?
- is the financial result a public screen or an audited budget?

## 7. What the numbers can and cannot support

What is strong:

- block geometry and estate coverage;
- WS4 runtime and scenario reproducibility;
- production, account, target and patch reporting;
- P00/P01 operational feasibility screens;
- public haul and fleet screening;
- public cost/price accounting.

What is provisional:

- the 100-year harvest level as an AAC;
- the financial result as a budget;
- the absence of a complete non-timber constraint set;
- the rolling full-year haul as a continuous truck schedule;
- the relationship between the model's opening pattern and operational layout.

What must not be claimed:

- that `low-44` is an approved AAC;
- that the NPV is an audited financial forecast;
- that the current scenarios carry every MKRF ecological constraint;
- that the rolling haul aggregate is a continuous 365-day schedule.

## 8. What field and data work would buy

For MKRF, the highest-value next work is not more dashboard. It is:

1. confirm the current management zones and non-timber constraints with MKRF
   staff;
2. review the opening-size and patch metrics against operational layout;
3. validate the cost and price bases against the public accounting boundary;
4. test a continuous multi-day haul schedule rather than monthly windows;
5. complete a sensitivity analysis on the target weights and growing-stock
   floor.

The existing data are sufficient to review scenario direction tomorrow. They
are not sufficient to sign a final plan.

## 9. Staged workplan

### Before the review

- Circulate this brief and the three-instance portal.
- Confirm that `low-44` is the scenario to open first.
- Confirm the P00/P01 operational handoff is the right first-decade story.

### After the review

- Add MKRF staff review of zones and constraints.
- Build the missing ecological constraint case.
- Refresh the financial and operational evidence before any external release.

### Decision gate

Do not move from “draft scenario screen” to “approved management plan” until
the non-timber constraints, AAC interpretation, and financial boundary are
reviewed.

## 10. What we are asking for

We are asking UBC Research Forests leadership and the Dean's Office to:

1. endorse this as the draft MKRF management-plan structure;
2. support a focused review of zones, constraints and the low/base/high scenario
   family;
3. treat the current results as a public planning screen, not an approved AAC or
   budget.

## Appendix A — Run register

| Run | Role |
| --- | --- |
| `mkrf-full-estate` | base-44 full-estate WS4 handoff |
| `mkrf-low-estate` | low-44 full-estate scenario |
| `mkrf-high-estate` | high-44 full-estate scenario |
| `mkrf-p00-operational` | base-44 P00 operational handoff |
| `mkrf-low-p00-operational` | low-44 P00 operational handoff |
| `mkrf-high-p00-operational` | high-44 P00 operational handoff |
| `mkrf-low-p01-operational` | low-44 P01 operational handoff |
| `mkrf-high-p01-operational` | high-44 P01 operational handoff |
| `mkrf-low-p01-haul-30d` | actual 30-day Phase I/II haul sample |
| `mkrf-low-p01-haul-year` | rolling full-year Phase I + monthly Phase II samples |

## Appendix B — Evidence paths

```text
fhops-public-demo/examples/demo_runs/MKRF_DECISION_PACK.md
fhops-public-demo/examples/demo_runs/MKRF_SCENARIOS.md
fhops-public-demo/examples/demo_runs/MKRF_SCENARIO_COMPARISON.md
fhops-public-demo/examples/demo_runs/mkrf-full-estate/
fhops-public-demo/examples/demo_runs/mkrf-low-estate/
fhops-public-demo/examples/demo_runs/mkrf-high-estate/
```

## Appendix C — What not to say

Do not say:

- “This is the approved MKRF AAC.”
- “This is an audited budget.”
- “The scenarios carry every ecological constraint.”
- “The rolling haul is a continuous 365-day plan.”

Say instead:

- “This is a reproducible 100-year public scenario screen.”
- “Low-44 is the recommended first review case.”
- “The numbers are planning evidence, not an approval.”
