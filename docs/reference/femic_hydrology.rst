FEMIC Hydrology Response Bundles
================================

FHOPS consumes versioned FEMIC hydrology response bundles. It does not run
FEMIC discovery, frequency fitting, surrogate training, or flood-risk
calculation, and it does not import WS4 at runtime.

Bundle Contract
---------------

A FEMIC hydrology bundle contains ``manifest.json`` and
``artifacts/<role>/<role>.json``. FHOPS validates and pins:

- ``bundle_id`` and ``bundle_version``;
- the manifest SHA-256;
- every artifact role, schema, media type, size, and SHA-256;
- path containment inside the bundle;
- the response-surface, flood-risk, domain, and disturbance-ledger identities;
- the producer caveats and consumer contract; and
- optional validation-report and model-card evidence.

Required roles are ``response_surface``, ``flood_risk``, ``domain``, and
``disturbance_ledger``. Optional roles include the validation report, model
card, pilot run, frequency fits, and surrogate artifacts.

Python Usage
------------

.. code-block:: python

   from pathlib import Path

   from fhops.scenario.hydrology import (
       assess_femic_hydrology_readiness,
       bundle_pin,
       load_femic_hydrology_bundle,
   )

   bundle = load_femic_hydrology_bundle(
       Path("data/femic/hydrology-response-2026.10.0"),
       expected_bundle_id="hydro-response-example",
       expected_bundle_version="2026.10.0",
   )
   pin = bundle_pin(bundle)
   readiness = assess_femic_hydrology_readiness(bundle)

   print(pin["manifest_sha256"])
   print(readiness.status)

Readiness
---------

``assess_femic_hydrology_readiness`` reports:

- ``not_available``: no validation report or model card is packaged;
- ``provisional``: evidence exists but the model card is not reviewed;
- ``conditionally_ready``: reviewed with conditions;
- ``ready``: reviewed, with a recorded hydrologist review and no tail-check
  failures;
- ``blocked``: a tail-check failure is recorded.

Missing evidence is reported as missing, never approved. A checksum pass is not
a hydrologic validation. Phase 15 uses these states for screening policy; the
validator itself does not grant operational use.

Scenario Pin
------------

Register a validated bundle in a scenario without copying it::

   fhops scenario hydrology register scenarios/example/scenario.yaml \
     data/femic/hydrology-response-2026.10.0

The scenario gains an optional ``hydrology_products`` section::

   hydrology_products:
     - bundle_id: hydro-response-example
       bundle_version: 2026.10.0
       manifest_sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
       domain_id: example-domain
       ledger_id: example-ledger
       response_surface_id: example-surface
       manifest_path: ../../data/femic/hydrology-response-2026.10.0/manifest.json
       readiness_status: ready
       readiness_evidence_sha256: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
       artifacts:
         - role: response_surface
           relative_path: artifacts/response_surface/response_surface.json
           schema_version: femic.hydrology.flood_response.v1
           media_type: application/json
           size_bytes: 1234
           sha256: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
       caveats:
         - Screening only; not a regulatory flood map.

The pin records the bundle identity, manifest and artifact checksums, domain,
ledger, response surface, readiness state, and caveats. It is a reference; the
bundle is not copied into the scenario or repository. Re-registering the same
pin is idempotent; reusing the same bundle id/version with a different manifest
checksum is rejected. Existing scenarios without the section remain valid.

Use ``--dry-run`` to validate and print the pin without writing the scenario.

Support Mapping
--------------

Hydrology mapping is an explicit crosswalk. A CSV row names exactly one FHOPS
support key and one FEMIC unit/watershed/receptor:

.. code-block:: text

   block_id,landing_id,road_id,unit_id,watershed_id,receptor_id,notes
   B01,,,unit-1,watershed-1,receptor-1,block review
   ,L01,,unit-1,watershed-1,receptor-1,landing review
   ,,R01,unit-1,watershed-1,receptor-1,road review

Review metadata is a separate JSON document:

.. code-block:: json

   {
     "schema_version": "fhops.hydrology.crosswalk.v1",
     "crosswalk_id": "crosswalk-example",
     "created_utc": "2026-10-27T00:00:00+00:00",
     "review_status": "reviewed",
     "reviewed_by": "reviewer-id",
     "method": "Manual block/landing/road review",
     "source": "Reviewed FEMIC domain bundle",
     "caveats": ["Screening crosswalk only."]
   }

The optional ``crosswalk_sha256`` field pins the CSV. Missing metadata is
recorded as ``not_reviewed`` and the mapping is provisional.

Map the scenario:

.. code-block:: bash

   fhops scenario hydrology map scenarios/example/scenario.yaml \
     data/femic/hydrology-response-2026.10.0 \
     reviewed-crosswalk.csv \
     --metadata reviewed-crosswalk.meta.json \
     --out build/hydrology_mapping

The command requires the bundle to be pinned in the scenario. It checks every
FHOPS block, landing, and road-construction id, every FEMIC unit/watershed/
receptor id, and the unit-to-watershed assignment. Complete coverage is required
unless ``--allow-partial`` records the gaps. The output is
``hydrology_mapping.csv`` plus ``hydrology_mapping.json`` with the bundle pin,
crosswalk checksum, review state, rows, coverage, warnings, and caveats.

No centroid, buffer, nearest-watershed, or nearest-road operation is performed.

CLI
---

Validate a delivered bundle without modifying a scenario::

   fhops scenario hydrology validate data/femic/hydrology-response-2026.10.0

   fhops scenario hydrology validate data/femic/hydrology-response-2026.10.0 \
     --expected-bundle-id hydro-response-example \
     --expected-bundle-version 2026.10.0

The command emits a deterministic JSON report and exits non-zero on an invalid
bundle. Use ``--no-verify-checksums`` only for a diagnostic inspection; the
default verifies every size and SHA-256.

Limits
------

P15.1 validates structure and pins producer evidence. It does not map FHOPS
blocks, landings, or roads to FEMIC watersheds, does not screen a schedule, and
does not create a flood map or regulatory result. The committed synthetic
fixture is ``tests/fixtures/hydrology/response`` and is not a real watershed or
gauge record.

Later Phase 15 tasks add scenario registration, an explicit crosswalk,
schedule-bound road/culvert exposure, and one-schedule screening.
