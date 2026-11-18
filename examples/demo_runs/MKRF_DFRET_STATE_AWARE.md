# MKRF state-aware residual-area scenarios

Status: **state-aware residual-area proxy; not yet a species/DBH tree-level residual selector and not a decision-grade plan.**

| Scenario | Residual area | Gross | Production | Net after all cost | Net after harvest cost | Gross NPV 4% | Net NPV 4% | Targets met/below/above |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| no-retention | 0 ha | CAD 716.7M | 3.38M m³ | CAD 403.7M | CAD 217.8M | CAD 182.6M | CAD 100.9M | 31/5/1 |
| low-44-state | 1,567 ha | CAD 482.1M | 2.27M m³ | CAD 230.1M | CAD 105.2M | CAD 126.2M | CAD 59.3M | 32/4/1 |
| base-44-state | 2,055 ha | CAD 421.6M | 1.99M m³ | CAD 181.4M | CAD 72.1M | CAD 106.9M | CAD 45.2M | 21/15/1 |
| high-44-state | 2,652 ha | CAD 324.8M | 1.54M m³ | CAD 111.8M | CAD 27.3M | CAD 81.6M | CAD 27.6M | 21/15/1 |

## What is now carried in the state

- Each no-retention block fragment is split into a harvested portion and a residual portion. The split is the largest-DF **value-equivalent area** from the pinned MKRF 684 profile.
- The residual portion is on its own track, with copied feature curves. It ages and grows through the 100-year horizon, but has no scheduled product treatment and is not re-entered in this screen.
- The harvested product curves carry the residual value/volume reduction and a fixed-cost correction. Gross, production, harvest cost, total cost and net revenue therefore reconcile with the earlier product-ledger screen at the same schedule.
- The target search was rerun with the same seed (44), target set (`targets_risk_cost_opt.yaml`), route configuration, topology, patch accounts and 100-year horizon.

## Results

The state-aware run preserves the product-ledger economics:

| Scenario | State gross | Product-screen gross | State volume | Product-screen volume | State net | Product-screen net | State targets | Product-screen targets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| low-44-state | CAD 482.1M | CAD 482.1M | 2.27M m³ | 2.27M m³ | CAD 230.1M | CAD 230.1M | 32/4/1 | 31/5/1 |
| base-44-state | CAD 421.6M | CAD 421.6M | 1.99M m³ | 1.99M m³ | CAD 181.4M | CAD 181.4M | 21/15/1 | 21/15/1 |
| high-44-state | CAD 324.8M | CAD 324.8M | 1.54M m³ | 1.54M m³ | CAD 111.8M | CAD 111.8M | 21/15/1 | 21/15/1 |

The low case resolves one additional feature-yield target because the residual cohort remains in the state and continues to age; base and high retain the same target status.

## Limits

- The residual area is a **value-equivalent area proxy**, not a measured stem footprint. It is larger than the physical area that would be occupied by a scattered largest-DF retention cohort.
- Species/DBH selection is still represented by the pinned MKRF 684 profile, not by a full-estate tree list.
- The residual track has no scheduled re-entry or partial harvest during the horizon. A production implementation needs an explicit residual state, re-entry rule and tree-level residual selector.

Files: `MKRF_DFRET_STATE_AWARE.csv`, `MKRF_DFRET_REOPTIMIZED.csv`, `MKRF_DFRET_REOPTIMIZED.md`, `MKRF_RETENTION_AUDIT.md`.
