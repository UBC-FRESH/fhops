# Phase 15 — Consume FEMIC hydrology response bundles

Status: planned (2026-10-26)
Parent issue: #218
Branch: `feature/phase15-hydrology-consumer`
Roadmap: `ROADMAP.md`, section "Phase 15 — Consume FEMIC hydrology response bundles"

## Context

FEMIC produces versioned hydrology response and flood-risk bundles. WS4 now
validates, pins, maps, preflights, and screens those bundles, and can consume an
explicit schedule-bound road/culvert exposure table. FHOPS P14 has completed the
FEMIC LidarBC consumer path, so the operational planning side no longer has a
blocking dependency.

The Chapman Creek pilot remains closed as data-blocked in FEMIC. Seymour River
still depends on the ungauged domain audit and has no reviewed bundle. Phase 15
therefore uses synthetic or public fixtures only and produces no real watershed
result.

## Decision

Phase 15 is a read-only FHOPS consumer and one-schedule screening phase.

It will:

- pin and validate a FEMIC hydrology bundle;
- register the pin in a FHOPS scenario;
- map FHOPS blocks, landings, and roads through an explicit reviewed crosswalk;
- load an explicit, schedule-bound road/culvert exposure table;
- screen one schedule and report per-watershed, per-receptor, per-period rows;
- refuse when evidence is incomplete, unreviewed, blocked, or inconsistent.

It will not:

- run FEMIC or import WS4 at runtime;
- infer watersheds, receptors, road state, or culvert locations from geometry;
- build a new flood model, response surface, or damage curve;
- integrate flood exposure into the optimizer in this phase;
- claim a current flood baseline, flood map, or regulatory result.

The shared exposure contract is `ws4.hydrology.exposure.v1`. FHOPS validates the
schema independently; it does not import WS4 code.

## Data flow

```text
FEMIC hydrology bundle
  -> FHOPS validate + pin
  -> scenario hydrology_products pin
  -> explicit crosswalk (blocks/landings/roads -> units/watersheds/receptors)
  -> schedule-bound exposure table
  -> one-schedule flood-risk screen
  -> screening CSV + manifest + caveats
```

The scenario stores references and checksums, not a copy of the bundle. The
crosswalk and exposure table are explicit inputs, not derived products.

## Bundle contract

The manifest schema is `femic.hydrology.response.v1`. Required artifact roles:

- `response_surface`;
- `flood_risk`;
- `domain`;
- `disturbance_ledger`.

Optional roles include `validation_report`, `model_card`, `pilot_run`, and the
frequency/surrogate artifacts already defined by FEMIC.

The validator checks:

- manifest and role schemas;
- path containment, declared size, and SHA-256;
- response-surface and flood-risk identity, row counts, and ratios;
- domain and ledger IDs;
- the producer consumer contract and caveats.

Missing readiness evidence is reported as missing, never approved. A tail-check
failure blocks use.

## Crosswalk contract

A crosswalk row names one FHOPS support key and one FEMIC mapping:

```text
block_id, landing_id, road_id, unit_id, watershed_id, receptor_id, notes
```

Exactly one support key is set. The mapping is explicit and reviewed. Coverage
must be complete unless `--allow-partial` records the gaps. Unknown IDs,
conflicting mappings, and a mismatch between the FEMIC unit and watershed fail.

Review metadata is a separate JSON document with a checksum, review status, and
reviewer. Unreviewed mappings remain provisional and cannot pass a
`require_reviewed` policy.

No centroid, buffer, nearest-watershed, or nearest-road operation is allowed.

## Exposure contract

FHOPS consumes the shared `ws4.hydrology.exposure.v1` table. It declares:

- the watershed IDs and periods;
- a complete watershed/period grid;
- road built, used, and decommissioned length;
- culvert count and exposed count;
- `source_id`, `review_status`, `reviewer_id`, and `schedule_sha256`;
- caveats.

Raw features are preserved. Densities are calculated from the FEMIC watershed
area. A missing row is an error, not zero. A schedule-hash mismatch refuses. A
fixed table is valid for one schedule only and must not be reused across
optimizer candidates.

## Screening and readiness

The screen selects the applicable response scenario from the harvest fraction
and exposure features. It emits one row per watershed, receptor, and period, and
records refusals rather than extrapolating.

Readiness policies:

- `allow_provisional`: allow missing/provisional evidence with warnings, but a
  tail-check block still refuses;
- `require_reviewed`: allow `ready` or `conditionally_ready`;
- `require_ready`: allow `ready` only.

Every output is screening-only and carries the producer caveats. A screen is not
a regulatory flood map or an operational safety determination.

## Fail-closed rules

- A valid checksum is not a hydrologic validation.
- Missing evidence is not approval.
- A crosswalk is not a spatial join.
- A partial mapping is a recorded gap, not complete coverage.
- A fixed exposure table is valid for one schedule only.
- The optimizer must not reuse a fixed table across candidates.
- No output may claim a current flood baseline, flood map, or regulatory result.

## Data preconditions for a later real pilot

1. A reviewed FEMIC response bundle for the watershed.
2. A current or governed gauge series, or explicit acceptance of a
   historical-only result.
3. A DEM with consistent horizontal and vertical metadata and bounded gaps.
4. Reviewed receptor geometry and capacity/damage evidence.
5. A reviewed FHOPS-to-FEMIC crosswalk.
6. Road and culvert evidence if the response surface uses those features.
7. Hydrologist review of the model card and record discontinuities.

Public data do not need an external governance gate. Non-public, Indigenous, or
licence-restricted data need the applicable governance decision before use.

## Tasks

- P15.1: define the bundle consumer contract and validation.
- P15.2: register and pin a bundle in a scenario.
- P15.3: map FHOPS support to watersheds and receptors.
- P15.4: load schedule-bound road/culvert exposure.
- P15.5: screen one schedule and gate on readiness.
- P15.6: prove the path, document, and close out.

## Acceptance

- A valid bundle pins every required artifact by checksum and size.
- A scenario pin reloads only when the manifest and artifacts still match.
- Every in-scope FHOPS support maps explicitly or records a gap.
- Exposure is reviewed and bound to one schedule.
- A schedule produces deterministic rows and explicit refusals.
- Missing, unreviewed, or blocked evidence refuses.
- The fixture covers success and fail-closed paths.
- Docs and the FHOPS quality suite are green.
- No real watershed or regulatory result is claimed.

## P15.1 contract decision

The consumer lives in `fhops.scenario.hydrology` and validates the FEMIC
manifest without importing WS4. It checks required roles, path containment,
declared sizes and SHA-256, role schemas, response/flood-risk/domain/ledger
identities, and optional readiness evidence. The CLI entry is
`fhops scenario hydrology validate`.

The committed synthetic bundle is `tests/fixtures/hydrology/response`. It is a
contract fixture, not a real watershed.

## P15.2 registration decision

The scenario pin lives in `hydrology_products` and records the bundle identity,
manifest checksum, domain/ledger/response-surface ids, manifest path,
readiness state, artifact checksums, caveats, and the producer consumer
contract. Registration is idempotent and rejects the same bundle id/version
with a different manifest checksum. The bundle is referenced, not copied.

## P15.3 crosswalk decision

Mapping is an explicit CSV crosswalk with one FHOPS support key per row and a
separate review-metadata document. The mapper checks block/landing/road ids,
FEMIC unit/watershed/receptor ids, and the ledger's unit-to-watershed
assignment. Complete coverage is required unless `--allow-partial` records the
gaps. The output is a row CSV plus a manifest; it is not a spatial join and is
not written into the scenario.

## P15.4 exposure decision

FHOPS consumes the shared `ws4.hydrology.exposure.v1` table and validates it
independently. The table declares a complete watershed/period grid, review
metadata, and a schedule hash. FHOPS binds it to an assignments CSV and refuses
a mismatch. Raw features are preserved; density features are calculated from
the FEMIC watershed area. The `fhops scenario hydrology exposure` command
validates the table against an optional assignments CSV. No road or culvert
geometry is inferred.

## P15.5 screening decision

Screening is one schedule at a time. It computes cumulative block area from the
schedule assignments and block GeoJSON/LiDAR support area, maps it to FEMIC
watershed area, uses the zero-based exposure period (`day - 1`), and selects the
response scenario from harvest plus exposure features. Missing block area,
mapping, exposure period, scenario, or flood-risk row is a refusal.

`require_reviewed` requires a reviewed bundle, crosswalk, and exposure table;
`require_ready` requires the bundle to be fully ready. A tail-check block always
refuses. The screen writes a CSV and manifest, carries the exposure digest and
the producer caveats, and is not wired into the optimizer.

## P15.6 closeout decision

The end-to-end integration test runs the CLI path from bundle validation through
registration, mapping, exposure validation, and one-schedule screening. The
phase is queued for approval with `notes/reports/p15-closeout.md`. No real
watershed result is claimed. Optimizer-integrated exposure remains deferred
until a reviewed bundle and schedule-derived road-state contract exist.

## Open decisions and recommended defaults

- **Exposure schema:** reuse `ws4.hydrology.exposure.v1` rather than create a
  divergent FHOPS schema. Recommended because both consumers then validate the
  same public contract.
- **CLI surface:** put commands under `fhops scenario hydrology ...` to mirror
  the LidarBC consumer. Recommended for operator consistency.
- **Optimizer integration:** defer. A fixed table cannot represent every
  candidate schedule. Recommended until a schedule-derived exposure model and
  reviewed response surface exist.
