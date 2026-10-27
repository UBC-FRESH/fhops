# P18.1 — Hydrology documentation and reproducibility audit

Status: audit complete (2026-10-27)
Parent phase: #260
Task issue: #261

## Verdict

The hydrology path is **reference-documented but not user-reproducible end to
end**. A new user can follow individual contract/reference pages and run the
synthetic tests, but there is no single pinned path from FEMIC producer output
to a WS4 landscape screen and a FHOPS operational check with expected outputs.

This is a documentation gap, not a claim that the software is absent. It is also
not a real watershed result: Chapman is data-blocked and Seymour has no reviewed
bundle.

## Existing documentation inventory

### FEMIC

Guides:

- `docs/guides/hydrology-domain-contract.rst`
- `docs/guides/hydrology-data-bundle.rst`
- `docs/guides/hydrology-disturbance-ledger.rst`
- `docs/guides/hydrology-flood-frequency.rst`
- `docs/guides/hydrology-process-models.rst`
- `docs/guides/hydrology-response-bundles.rst`
- `docs/guides/hydrology-surrogate-models.rst`
- `docs/guides/hydrology-tier0-screening.rst`
- `docs/guides/hydrology-validation-closeout.rst`

Also present: contract/API pages under `docs/reference/contracts/` and
`docs/reference/api/`, plus P114/P118 planning and closeout notes.

Gap: the guides describe producer contracts and methods; they do not provide a
cross-repo consumer quickstart or a real-data acceptance path.

### WS4

Present:

- `docs/reference/femic-hydrology.rst`: bundle validation, registration,
  preflight, exposure, screening, readiness, and mapping.
- P57/P60/P62 closeout reports and design notes.
- CLI reference for the hydrology commands.

Gap: no tutorial that starts from a producer bundle and ends with a landscape
run, no public crosswalk/domain with FEMIC ledger units, and no real pilot.

### FHOPS

Present:

- `docs/reference/femic_hydrology.rst`: bundle validation, registration,
  crosswalk, exposure, screening, hazard windows, assets, constraint checks,
  and the solver boundary.
- P15/P16 closeout reports and phase notes.
- Synthetic fixtures under `tests/fixtures/hydrology/`.

Gap: no cross-repo quickstart, no version matrix, no expected-output walkthrough,
and no executable docs check.

## Gap matrix

| Area | Existing | Gap | Owner | Task | Type |
| --- | --- | --- | --- | --- | --- |
| Cross-repo entry point | Separate repo docs | No single quickstart from FEMIC to WS4 to FHOPS | FHOPS docs | P18.2 | Documentation |
| Version compatibility | Package releases/CHANGELOGs | No matrix of known-compatible FEMIC/WS4/FHOPS versions | FHOPS docs | P18.2 | Documentation |
| Shared fixture | Separate synthetic fixtures per repo | No common fixture with expected outputs across repos | FHOPS docs | P18.2 | Documentation |
| Contract index | Per-repo references | No single index of bundle, crosswalk, exposure, hazard, asset, and screen schemas | FHOPS docs | P18.3 | Documentation |
| Failure semantics | Scattered tests/errors | No consolidated refusal/failure table | FHOPS docs | P18.3 | Documentation |
| WS4 landscape tutorial | Reference page | No step-by-step landscape flood screening/optimization tutorial | WS4 docs | P18.2 + WS4 follow-up | Documentation |
| FHOPS operational tutorial | Reference page | No step-by-step hazard/asset/constraint-check tutorial | FHOPS docs | P18.2 | Documentation |
| Expected outputs | Test assertions | No user-facing expected CSV/JSON snippets | FHOPS docs | P18.2 | Documentation |
| Docs checks | Sphinx build/link checks | No executable command/link checker for the hydrology path | FHOPS docs/CI | P18.4 | Documentation |
| Troubleshooting | None consolidated | No FAQ for missing reviewer, schedule hash, mapping gaps, or policy refusal | FHOPS docs | P18.2/P18.3 | Documentation |
| Licence/provenance | Public-data guidance | No cross-repo licence/provenance matrix for hydrology inputs | FHOPS docs | P18.2/P18.3 | Documentation |
| Real watershed pilot | Chapman audit; Seymour audit | No current gauge/DEM vertical/receptor/crosswalk/hydrologist review | FEMIC/WS4 | data follow-up | Data/review |
| Solver-side hydrology | P16 boundary | FHOPS does not optimize watershed response | FHOPS | future phase | Capability |
| Hydrologist review | Pending | No review record or model-card interpretation guide | FEMIC/WS4 | review follow-up | Review |

## What a user can do today

- Install the packages and run unit/contract tests.
- Validate a synthetic FEMIC hydrology bundle.
- Register/map/screen with the committed synthetic fixtures.
- Run FHOPS hazard/asset/constraint checks on a synthetic schedule.
- Read the producer and consumer reference pages.

## What a user cannot do today

- Reproduce a real watershed flood-aware analysis from public data.
- Obtain a validated cross-repo fixture with expected outputs.
- Know which exact versions interoperate without reading commit history.
- Rely on a single contract index for schema and refusal behavior.
- Treat any output as a current flood baseline, flood map, or regulatory result.

## Recommended sequence

1. P18.2: pinned quickstart, version matrix, expected outputs, and explicit
   synthetic/real boundary.
2. P18.3: contract/schema index and failure matrix.
3. P18.4: executable docs checks.
4. P18.5: closeout and remaining data/review handoff.
