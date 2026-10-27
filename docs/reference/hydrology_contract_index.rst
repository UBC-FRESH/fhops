Hydrology Contract and Schema Index
===================================

This page is the single index for the hydrology contracts used across FEMIC,
WS4, and FHOPS. It names ownership, the key required fields, and the expected
failure behavior. The detailed field lists remain in the linked reference pages.

Contract Layers
---------------

.. list-table::
   :header-rows: 1

   * - Layer
     - Owner
     - Purpose
     - Canonical reference
   * - Producer data and response
     - FEMIC
     - Domain, bundles, ledgers, frequency fits, response surfaces, validation
     - FEMIC ``docs/guides/hydrology-*`` and ``docs/reference/contracts``
   * - Landscape consumer
     - WS4
     - Bundle pin, crosswalk, mapping, preflight, screening, exposure
     - :doc:`femic-hydrology`
   * - Operational consumer
     - FHOPS
     - Bundle pin, crosswalk, exposure, hazard, assets, screening, checks
     - :doc:`femic_hydrology`

A contract is not a watershed result. A structurally valid bundle can still be
unreviewed, and a screening row is not a regulatory flood determination.

FEMIC Producer Contracts
------------------------

.. list-table::
   :header-rows: 1

   * - Schema
     - Required content
     - Failure behavior
   * - ``femic.hydrology.sources.v1``
     - Source registry, licence/provenance, source ids
     - Unknown or missing source fails the domain audit
   * - ``femic.hydrology.domain.v1``
     - Domain id, watersheds, receptors, streams, roads, DEM metadata
     - Missing CRS, bounds, vertical evidence, or receptor support fails audit
   * - ``femic.hydrology.bundle.v1``
     - Bundle id/version, source registry, domain, ledger, provenance
     - Missing source, checksum, or licence fails the bundle audit
   * - ``femic.hydrology.disturbance.v1``
     - Ledger id, domain id, units, harvest/road events
     - Unknown unit/watershed or non-finite area/volume fails
   * - ``femic.hydrology.flood_frequency.v1``
     - Station id, fit method, parameters, return periods, diagnostics
     - Failed tail checks block operational use
   * - ``femic.hydrology.flood_response.v1``
     - Surface id, baseline, scenarios, return periods, response rows
     - Missing scenario/period row or inconsistent ratio fails
   * - ``femic.hydrology.flood_risk.v1``
     - Table id, source surface, receptor rows, baseline/scenario flows
     - Row-count, ratio, or source-surface mismatch fails
   * - ``femic.hydrology.validation.v1``
     - Validation id, tail-check failures, usable fits, benchmark counts
     - A recorded tail failure blocks use
   * - ``femic.hydrology.model_card.v1``
     - Model-card id, review status, validation summary, caveats
     - Missing review remains ``not_reviewed``; it is never approval
   * - ``femic.hydrology.response.v1``
     - Bundle manifest with pinned artifacts and required roles
     - Missing/extra/tampered artifact or wrong role schema fails
   * - ``femic.hydrology.screening.v1``
     - Tier 0 screening rows and caveats
     - Not a substitute for a process model or flood map
   * - ``femic.hydrology.process_result.v1``
     - Process scenario/results and diagnostics
     - Missing calibration/validation evidence remains a limitation
   * - ``femic.hydrology.surrogate_model.v1``
     - Surrogate design, training data, metrics, applicability domain
     - Out-of-domain queries refuse
   * - ``femic.hydrology.pilot.v1``
     - Pilot/benchmark run evidence
     - Unevaluated benchmarks are reported, not treated as passed

WS4 Landscape Consumer Contracts
--------------------------------

.. list-table::
   :header-rows: 1

   * - Schema
     - Required content
     - Failure behavior
   * - ``ws4.hydrology.crosswalk.v1``
     - Crosswalk id, checksum, review status, reviewer when reviewed
     - Missing/unknown support, conflicting unit/watershed, or unreviewed mapping under a reviewed policy fails
   * - ``ws4.hydrology.mapping.v1``
     - Bundle pin, crosswalk checksum, coverage, review state
     - Incomplete coverage fails unless partial mapping is explicit
   * - ``ws4.hydrology.preflight.v1``
     - Bundle, readiness, policy, mapping coverage, ``screening_ready``
     - Any blocking condition exits non-zero
   * - ``ws4.hydrology.screen.v1``
     - Screen id, bundle/mapping/schedule digests, rows, refusals
     - Out-of-tolerance or missing evidence refuses
   * - ``ws4.hydrology.exposure.v1``
     - Complete watershed/period grid, review, schedule hash, road/culvert rows
     - Missing/duplicate/undeclared row or schedule mismatch fails
   * - ``ws4.hydrology.flood_screen.v1``
     - Mapping, covariates, tolerance, refusal penalty, readiness policy
     - Fixed exposure is refused in optimizer use; missing mapping fails

FHOPS Operational Consumer Contracts
------------------------------------

.. list-table::
   :header-rows: 1

   * - Schema
     - Required content
     - Failure behavior
   * - ``Scenario.hydrology_products``
     - Bundle pin, domain/ledger/surface ids, artifact checksums, readiness
     - Missing or changed pin fails registration/reload
   * - ``fhops.hydrology.crosswalk.v1``
     - Support key, FEMIC unit/watershed/receptor, review metadata
     - Unknown/conflicting support, incomplete coverage, or unreviewed policy fails
   * - ``fhops.hydrology.mapping.v1``
     - Bundle pin, crosswalk checksum, rows, coverage, review state
     - Missing/incomplete mapping refuses screening and checks
   * - ``ws4.hydrology.exposure.v1``
     - Schedule hash, complete watershed/period grid, review, road/culvert rows
     - Missing/duplicate row or schedule mismatch fails
   * - ``fhops.hydrology.hazard.v1``
     - Hazard id, reviewed watch/warning/closure windows, caveats
     - Bad days, duplicate/overlap rules, or missing review metadata fail
   * - ``fhops.hydrology.assets.v1``
     - Explicit road/culvert ids, watersheds, vulnerability, review
     - Unknown road job/watershed or duplicate asset fails
   * - ``fhops.hydrology.screen.v1``
     - One-schedule rows, refusals, readiness policy, bundle/mapping/exposure pins
     - Missing features, evidence, or policy failure refuses
   * - ``fhops.hydrology.constraint_check.v1``
     - Schedule digest, hazard/mapping ids, events, failure state
     - Closure fails by default; missing mapping refuses

Shared Exposure Contract
------------------------

``ws4.hydrology.exposure.v1`` is owned by WS4 but consumed by FHOPS. It is a
schedule-bound road/culvert table, not a spatial product. The declared
watershed/period grid must be complete. A missing row is an error, not zero.
FHOPS validates the schema independently; it does not import WS4 at runtime.

Failure Matrix
--------------

.. list-table::
   :header-rows: 1

   * - Condition
     - Result
     - Owner
   * - Missing or malformed bundle manifest
     - Bundle validation fails; no consumer can pin it
     - FEMIC producer
   * - Tail-check failure
     - Readiness ``blocked``; operational use refuses
     - FEMIC producer
   * - Missing model card/review
     - ``not_available``/``provisional``; reviewed policy refuses
     - FEMIC producer + hydrologist
   * - Unreviewed or incomplete crosswalk
     - Mapping provisional or incomplete; reviewed policy refuses
     - WS4/FHOPS consumer owner
   * - Missing watershed/period exposure row
     - Exposure load/screen refuses
     - Input owner
   * - Exposure schedule hash mismatch
     - Screen refuses; regenerate for the exact schedule
     - Input owner
   * - Missing block area / mapping
     - Screen/check refuses
     - FHOPS scenario/crosswalk owner
   * - No matching response scenario
     - Screening refusal
     - FEMIC response + consumer inputs
   * - Closure hazard activity
     - Constraint check exits non-zero by default
     - FHOPS operational policy
   * - Fixed exposure in optimizer
     - Flood-screen config refuses
     - FHOPS design boundary

What Is Not a Contract
----------------------

- A synthetic quickstart is not a real watershed result.
- A Tier 0 screen is not a process model.
- A flood response surface is not a flood map.
- A constraint check is not an operational safety determination.
- A hydrologist review cannot be inferred from a checksum or review status.

Version Compatibility
---------------------

The tested source versions and the synthetic path are in
:doc:`../howto/hydrology_quickstart`. The package versions are not a guarantee
that every released wheel interoperates; pin the three versions together and
run the quickstart before a new analysis.
