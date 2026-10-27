# Phase 16 — Flood-aware operational constraints

Status: active (2026-10-27)
Parent issue: #235
Branch: `feature/phase16-flood-operational-constraints`
Roadmap: `ROADMAP.md`, section "Phase 16 — Flood-aware operational constraints"

## Context

FHOPS schedules machines, blocks, shifts, and road-work context at daily to
seasonal scale. It does not model watershed flood generation. FEMIC produces
the hydrology response, and WS4 is the landscape estate model where cumulative
harvest and road scenarios can change flood response.

A per-candidate watershed hydrology model inside the FHOPS search would be a
scale mismatch: daily machine moves do not drive peak flow at a watershed
outlet. What FHOPS can do is manage **operational exposure** against a fixed,
externally supplied hazard.

## Decision

Phase 16 adds flood-aware operational constraints, not flood-risk optimization.

It will:

- consume reviewed hazard windows by watershed and day;
- consume explicit road/culvert asset evidence;
- map block activity to watersheds through the P15 crosswalk;
- report watch, warning, and closure exposure events;
- refuse closure-window activity;
- apply fixed hazard constraints in the solver only where existing decision
  variables can support them.

It will not:

- compute watershed flood response;
- run hydrology per schedule or per optimizer candidate;
- create a flood map or damage curve;
- infer assets or watersheds from geometry;
- replace landscape-scale flood optimization in WS4/FEMIC.

## Scale boundary

| Decision scale | Flood effect | Owner |
| --- | --- | --- |
| Daily machine/shift scheduling | Local access and asset exposure; no meaningful watershed peak-flow change | FHOPS |
| Seasonal road use and closures | Operational risk against a fixed hazard window | FHOPS |
| Multi-year harvest/road trajectory | Cumulative land-cover and road effects on flood response | WS4/FEMIC |

The FHOPS constraint is: given a hazard scenario, avoid or penalize operational
activity that creates unacceptable exposure. It is not: optimize the watershed
flood response.

## Contracts

### Hazard windows

`fhops.hydrology.hazard.v1` declares:

- `hazard_id`, `generated_utc`, `source_id`;
- `review_status`, `reviewer_id` when reviewed;
- `windows`: watershed id, inclusive `start_day`/`end_day`, severity
  (`watch`, `warning`, `closure`), optional return period, optional source,
  notes;
- `caveats`.

A closure window outranks warning, which outranks watch. Overlapping windows for
the same watershed are allowed only when the higher severity is explicit and
consistent.

### Asset evidence

`fhops.hydrology.assets.v1` declares road and culvert assets:

- asset id and type (`road`, `culvert`);
- watershed id;
- optional road-job id;
- vulnerability class and notes;
- source and review metadata.

Assets are explicit. FHOPS does not infer them from geometry.

### Constraint check

`fhops scenario hydrology constraint-check` reads a scenario, mapping, schedule,
hazard table, and optional asset table. It emits:

- watch events;
- warning events;
- closure violations;
- per-day, machine, block, watershed, and asset detail;
- a manifest with review state, source digests, coverage, and caveats.

Exit behavior:

- `--fail-on-closure` (default) fails on closure activity;
- `--fail-on-warning` optionally fails on warning activity;
- watch events are informational.

## P16.1 hazard-window decision

The hazard table lives in `fhops.scenario.hydrology_hazard` and is validated
independently of FEMIC bundles. Windows are inclusive by day and use three
severities. Overlapping same-severity windows are rejected; different severities
are allowed and the highest applies. The CLI entry is
`fhops scenario hydrology hazard validate`.

## Solver integration

P16.4 audits the operational MILP and heuristics. It may add a fixed
closure-window prohibition and warning-window penalty if block/day/shift
variables are sufficient. If road-work timing is not a decision variable, that
limit is recorded and road/culvert constraints remain at the one-schedule check
layer.

The solver must never call a per-candidate hydrology model.

## Data preconditions for a real application

1. A reviewed hazard scenario with a clear forecast lead time.
2. Reviewed road/culvert inventory and vulnerability classes.
3. A reviewed block/landing/road crosswalk.
4. A FHOPS scenario with the road jobs and schedule horizon.
5. An operational policy for closure, warning, and watch windows.
6. Hydrologist and operations review before any safety or regulatory use.

## Tasks

- P16.1: hazard-window contract and validator.
- P16.2: road/culvert asset evidence.
- P16.3: one-schedule constraint check.
- P16.4: fixed solver constraints where supported.
- P16.5: fixture, docs, and closeout.

## Acceptance

- Hazard windows and assets validate review metadata and explicit ids.
- A schedule reports watch, warning, and closure events.
- Closure activity fails by default.
- Warning activity can fail under an explicit policy.
- Missing evidence refuses.
- Solver integration, if present, is fixed-scenario only.
- No real watershed, flood map, or regulatory result is claimed.
- FHOPS quality suite and docs build are green.
