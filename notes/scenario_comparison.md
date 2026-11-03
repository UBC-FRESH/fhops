# Studio scenario comparison page

Issue: #377. Branch: `issue-377-scenario-compare`.

## Purpose

Compare any two Studio projects/runs without mixing their histories:

- KPIs and warning counts,
- freshness,
- machine busy time/utilization,
- truck dispatches and landing stockpiles,
- per-landing inventory.

## Usage

Open `/studio/compare` and choose left/right projects and runs. Selections are
stored in query parameters, so a comparison can be shared:

```text
/studio/compare?left_project=<id>&left_run=<run>&right_project=<id>&right_run=<run>
```

## Demo comparison

- Left: CTL run `20261103T080119Z` (H1 harvester, H2/H3 forwarders, H4/H4-B loaders).
- Right: full-tree comparator `20261103T082443Z` (same terrain, retention,
  landings, trucks, and 300% grade limit; feller-buncher + skidders + processors).

Results:

| Metric | CTL | Full tree |
|---|---:|---:|
| Trees | 553 | 553 |
| Volume | 776 m³ | 776 m³ |
| Makespan | 20.3 h | 18.8 h |
| Warnings | 0 | 0 |
| Truck loads | 25 | 25 |

The CTL forwarders are the critical path (about 15.6 h busy each); full-tree
processors are the critical path (about 14.0 h / 10.1 h).

## Tests

- Studio app route smoke test.
- Existing run/project API tests.
- JS syntax check.
