# MKRF no-retention / residual overlay

Status: **overlay on a no-retention WS4 baseline; not yet a re-optimized residual-retention search**.

The no-retention matrix was rebuilt, its product curve bank was repaired against the canonical matrix, and the target search completed. The largest-DF value/volume profile from the pinned MKRF 684 tree list was then applied to the no-retention gross and volume.

| Scenario | Retained fraction | Residual value share | Gross baseline | Residual gross | Gross change | Volume baseline | Residual volume | Net after all cost baseline | Net after all cost residual | NPV4 gross baseline | NPV4 gross residual | NPV4 net baseline | NPV4 net residual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| low-44-dfret | 4.39% | 32.6% | CAD 716.7M | CAD 483.2M | -32.6% | 3.38M m³ | 2.28M m³ | CAD 403.7M | CAD 230.9M | CAD 182.6M | CAD 123.1M | CAD 100.9M | CAD 57.7M |
| base-44-dfret | 8.79% | 42.7% | CAD 716.7M | CAD 410.6M | -42.7% | 3.38M m³ | 1.94M m³ | CAD 403.7M | CAD 176.9M | CAD 182.6M | CAD 104.6M | CAD 100.9M | CAD 44.2M |
| high-44-dfret | 15.72% | 55.1% | CAD 716.7M | CAD 321.6M | -55.1% | 3.38M m³ | 1.52M m³ | CAD 403.7M | CAD 110.7M | CAD 182.6M | CAD 81.9M | CAD 100.9M | CAD 27.7M |

The retained fraction is the current area-retention share, used here as a proxy for the residual stem fraction. The value/volume split is the MKRF 684 largest-DF profile. This is a high-grading overlay, not a replacement for a species/DBH-aware residual operator.

The no-retention product curve table was repaired by mapping the canonical product/feature curves onto the no-retention tracks; this fixed the 482-curve collapse and restored separate LogValue, harvest cost and NetRevenue accounts.

Files: `MKRF_DFRET_SCENARIOS.csv`, `MKRF_RETENTION_AUDIT.md`, `MKRF_RETENTION_PROFILE.csv`.
