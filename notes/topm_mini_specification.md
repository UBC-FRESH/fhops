# `topm-mini` Executable Specification

Date: 2026-09-24
Issues: #36, #37
Machine-readable source: `tests/fixtures/tactical_operational/topm-mini/specification.yaml`

## Purpose

`topm-mini` is the copyright-safe acceptance fixture for Phase 6. It is small enough to verify by
hand but covers the structural behaviors that distinguish TOPM-like planning from the current
operational scheduler:

- multi-period tactical–operational time;
- block × system × period harvest alternatives;
- continuous, semi-continuous, and whole-block harvest modes;
- product-specific yields;
- facility demand and initial inventory;
- transport arcs and outside purchases; and
- hand-calculated objective and balance outcomes.

## What this fixture is not

- It is not a copy of Oborn's YFP data, OperMAX data, or any other restricted appendix.
- It is not a performance benchmark.
- It is not a complete tactical scenario contract implementation; it is the executable design
  target that issue #38 will turn into validators and loaders.

## Current hand-calculated checks

### Harvest activation modes

The fixture specifies four basic outcomes:

1. A continuous mode may harvest 2.5 ha on `B1__ground_fb_skid__Y1-P1`, yielding 200 m³ sawlog and
   50 m³ pulp.
2. A semi-continuous mode rejects a 1.5 ha request on that option because the minimum active cut is
   2.0 ha.
3. The same semi-continuous option accepts exactly 2.0 ha, yielding 160 m³ sawlog and 40 m³ pulp.
4. A whole-block mode on `B3__ground_fb_skid__Y1-P1` converts any activation into the full 4.0 ha
   operable area, yielding 240 m³ sawlog and 80 m³ pulp.

### Economic dispatch

For 780 m³ of required Y1-P1 sawlog, the hand-calculated least-cost dispatch is:

| Option | Area (ha) | Sawlog (m³) | Total volume incl. pulp (m³) | Fixed cost | Variable cost |
|---|---:|---:|---:|---:|---:|
| `B2__ground_fb_skid__Y1-P1` | 4.00 | 360 | 480 | 80 | 8,640 |
| `B1__ground_fb_skid__Y1-P1` | 5.25 | 420 | 525 | 100 | 10,500 |
| **Total** | **9.25** | **780** | **1,005** | **180** | **19,140** |

Total harvest cost: **19,320 CAD_2026**. Transport and purchase costs are deliberately excluded from
this isolated harvest-dispatch check.

### Integrated flow and inventory balances

The current integrated `topm-mini` optimum uses opening mill inventory before harvesting more wood:

- sawmill: opening 50 + deliveries 730 + purchases 0 − consumption 780 = closing 0;
- pulp mill: opening 20 + deliveries 160 + purchases 0 − consumption 180 = closing 0.

The resulting Phase 6.3 objective is **24,130 CAD_2026**: harvest fixed 180, harvest variable
18,000, transport 5,950, and purchases 0. Harvest dispatch is B1 = 6.0 ha and B2 ≈ 2.7778 ha.
Future implementations must reconcile every product/facility/period balance independently.

## Acceptance use by later issues

- **#38** turns this YAML into validated contract objects and fails clearly on missing IDs,
  duplicate keys, invalid units, impossible windows, and inconsistent yields.
- **#39** reproduces the harvest-mode and economic-dispatch expectations with the aggregate MILP
  (`fhops.model.milp.tactical_operational`).
- **#40** reproduces the product-flow and facility-inventory expectations in the integrated MILP.
- **#41–#44** may extend the fixture with roads, silviculture, fleet investment, overlays, and
  rolling-state handoffs, but must keep these original checks passing.

## Validation hook

`tests/test_topm_mini_specification.py` provides the immediate structural check. It verifies that
the YAML remains parseable, internally linked, and consistent with the hand-calculated cases while
the real tactical contract and MILP are implemented.
