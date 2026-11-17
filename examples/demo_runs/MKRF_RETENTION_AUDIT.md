# MKRF retention-value audit

Status: **audit and sensitivity, not a re-optimized WS4 scenario**.

## Finding

WS4's ForestModelXML `<retention>` rule is implemented as an **area split**. The compiler moves a fraction of an eligible fragment's area to an unmanaged state. It does not select species, DBH, or the largest Douglas-fir stems. The retained area therefore removes an average area slice, not a high-graded residual cohort.

This explains why the current low/base/high numbers move mainly with retained area: gross log value per managed hectare is nearly constant across the variants. The model is not representing the operational prescription described as ‘leave the biggest Douglas-fir’.

## Audit tree list

`mkrf_684` has **4,798** pinned trees, **3,542** Douglas-fir, 4,116.6 m³ merchantable volume and CAD 434,150 gross log value (CAD 105.46/m³, game price deck).

The tree list is synthetic and represents one stand; it is used here to measure the value profile, not as an estate inventory.

| Fraction of all stems | Selected largest DF | Volume share | Gross-value share |
| ---: | ---: | ---: | ---: |
| 5% | 240 | 32.6% | 32.6% |
| 10% | 480 | 45.9% | 46.0% |
| 15% | 720 | 54.1% | 54.3% |
| 20% | 960 | 59.8% | 60.1% |
| 30% | 1,439 | 66.8% | 67.3% |

## Sensitivity method

- Current WS4 low/base/high schedules are treated as the **area-retention** case.
- The current retention-area fraction is used as a proxy for the fraction of stems left as residual.
- Residual stems are selected as the largest Douglas-fir from the MKRF 684 tree list, then the resulting value and volume shares are applied to the current schedule's potential gross/volume.
- Potential gross and volume add back the average retained area slice. This isolates the difference between average-area retention and largest-DF stem retention.
- Harvest cost is scaled with harvested volume; other costs are held fixed. No schedule is re-optimized and no target is re-run.

## Corrected scenario numbers

| Scenario | Retention ha | Gross current | Gross corrected | Δ gross | Volume current | Volume corrected | Net after all cost current | Net after all cost corrected | NPV4 gross current | NPV4 gross corrected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| low-44 | 181.1 | CAD 673.3M | CAD 474.8M | -29.5% | 3.17M m³ | 2.23M m³ | CAD 380.2M | CAD 233.3M | CAD 92.4M | CAD 65.2M |
| base-44 | 362.1 | CAD 668.2M | CAD 419.7M | -37.2% | 3.15M m³ | 1.98M m³ | CAD 376.8M | CAD 192.7M | CAD 92.1M | CAD 57.8M |
| high-44 | 647.6 | CAD 592.6M | CAD 315.6M | -46.8% | 2.79M m³ | 1.49M m³ | CAD 334.5M | CAD 128.9M | CAD 81.6M | CAD 43.5M |

The public **net-after-harvest-cost** convention is retained in `MKRF_RETENTION_VALUE_SCENARIOS.csv`; it is lower because the existing public comparison subtracts harvest cost from the already netted revenue account. The table above uses **net after all cost** to avoid that double-counting.

| Scenario | Current net NPV 4% | Corrected net NPV 4% |
| --- | ---: | ---: |
| low-44 | CAD 48.3M | CAD 25.9M |
| base-44 | CAD 48.2M | CAD 19.9M |
| high-44 | CAD 42.5M | CAD 11.0M |

## Why the correction is material

Retained area is only 4.4%, 8.8% and 15.7% of the eligible area, but the largest-DF profile represents 32.6%, 42.8% and 55.1% of gross value. Per retained hectare, the high-graded residual is about 7.4x, 4.9x and 3.5x the average value of the area slice in the low/base/high cases.

## Files

- `MKRF_RETENTION_VALUE_SCENARIOS.csv` — full current/corrected metrics
- `MKRF_RETENTION_AUDIT.md` — this report
- `MKRF_SCENARIO_COMPARISON.csv` — existing area-retention comparison

## Decision boundary

These corrected numbers show the direction and magnitude of the high-grading error. They are not an approved AAC, cash-flow forecast, or re-optimized plan. A production fix should make the retention operator species/DBH-aware, or apply an explicit residual-tree profile inside each harvested block, and then re-run the target search.
