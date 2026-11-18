# MKRF low-44 P01 decision pack

## Recommendation

Carry **`scenario-low-44`** forward.

| Metric | Low-44 |
| --- | ---: |
| Production | 3,170,458 m³ over 100 years |
| Net after harvest cost | CAD 205.9M |
| Annualized net after cost | CAD 2.06M/yr |
| NPV 2% | CAD 87.3M |
| NPV 4% | CAD 48.3M |
| NPV 6% | CAD 31.9M |
| Targets met/below/above | 33 / 3 / 1 |

Comparison at 4% NPV: low CAD 48.3M, base CAD 48.2M, high CAD 42.5M.

## Retention-value caveat

The current low/base/high runs are **area-retention** variants. WS4 does not
select the largest Douglas-fir stems; it moves a fraction of eligible area to
an unmanaged state. The reported finance is therefore an average-area screen,
not a high-graded residual prescription.

The audit in `MKRF_RETENTION_AUDIT.md` uses the pinned MKRF 684 tree list to
estimate the high-grading effect. The no-retention baseline is CAD 716.7M
gross, 3.38M m³, and CAD 403.7M net after all cost. The residual-product target
search gives:

- `low-44-dfret`: CAD 482.1M gross, 2.27M m³, CAD 230.1M net after all cost;
- `base-44-dfret`: CAD 421.6M gross, 1.99M m³, CAD 181.4M net after all cost;
- `high-44-dfret`: CAD 324.8M gross, 1.54M m³, CAD 111.8M net after all cost.

This is a product-ledger residual screen. The state transition still harvests
the full area and does not yet carry residual stems forward. Full detail is in
`MKRF_DFRET_REOPTIMIZED.md`.

## Operational evidence

- P00: 86 blocks, 367,238 m³, 296 days, zero remaining work.
- P01: 110 blocks, 303,770 m³, 269 days, zero remaining work.
- 30-day actual FHOPS Phase I/II: 49,934 m³ delivered, 1,110 truckloads, 37 day-1 loads, 12 trucks.
- Rolling full-year Phase I: 12 monthly windows, 303,765.7 m³ delivered, 8,295 truckloads.
- Rolling monthly Phase II day-1 samples: 282 scheduled loads across 12 monthly schedules.

## Caveats

The finance result is a public WS4 model projection, not a budget forecast. NPV uses annual cash flows
spread uniformly within 10-year periods. The rolling full-year haul is an aggregation of 12 monthly
Phase I windows plus one Phase II day sample per month, not a continuous 365-day truck schedule.
Road distances are a public-geography screen, not a surveyed network.

## Decision

If the faculty budget question is “what sustainable annual contribution can MKRF support?”, the
current public low-44 screen is approximately **CAD 2.06M/year net after harvest cost**, with a
4% NPV of about **CAD 48.3M**. Those are planning numbers, not an audited budget.
