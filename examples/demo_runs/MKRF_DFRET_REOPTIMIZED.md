# MKRF residual-retention scenarios

Status: **target-search results from the residual-product matrix; the state transition still harvests the full area and does not yet carry residual stems forward.**

| Scenario | Gross | Production | Net after all cost | Net after harvest cost | Gross NPV 4% | Net NPV 4% | Targets met/below/above |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| no-retention | CAD 716.7M | 3.38M m³ | CAD 403.7M | CAD 217.8M | CAD 182.6M | CAD 100.9M | 31/5/1 |
| low-44-dfret | CAD 482.1M | 2.27M m³ | CAD 230.1M | CAD 105.2M | CAD 126.2M | CAD 59.3M | 31/5/1 |
| base-44-dfret | CAD 421.6M | 1.99M m³ | CAD 181.4M | CAD 72.1M | CAD 106.9M | CAD 45.2M | 21/15/1 |
| high-44-dfret | CAD 324.8M | 1.54M m³ | CAD 111.8M | CAD 27.3M | CAD 81.6M | CAD 27.6M | 21/15/1 |

The residual matrices were built by scaling the **product yield, gross log value, harvest cost and net revenue curves** by the largest-DF profile from the pinned MKRF 684 tree list. The no-retention matrix supplies the baseline. This is a **finance/curve screen**, not the final state-aware residual implementation.

The residual share is applied through the product ledgers, and the target search was rerun with the same seed, target set, route configuration and 100-year horizon.

Files: `MKRF_DFRET_REOPTIMIZED.csv`, `MKRF_DFRET_SCENARIOS.csv`, `MKRF_RETENTION_AUDIT.md`.
