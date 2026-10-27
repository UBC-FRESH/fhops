# Phase 18 — Hydrology documentation and reproducibility

Status: active (2026-10-27)
Parent issue: #260
Branch: `feature/phase18-hydrology-docs`
Roadmap: `ROADMAP.md`, section "Phase 18 — Hydrology documentation and reproducibility"

## Why P18

P17 is already the tree-scale inventory and spatial-harvesting phase. This
documentation phase therefore uses P18 and keeps P17 unchanged.

## Goal

Make the FEMIC → WS4 → FHOPS hydrology path reproducible for a new user. This
is documentation and reproducibility work, not a new hydrology capability.

## What exists

- FEMIC hydrology guides and contract/API pages.
- WS4 hydrology consumer reference and P57/P60/P62 closeouts.
- FHOPS hydrology consumer reference and P15/P16 closeouts.
- Synthetic contract fixtures in all three repositories.

## What is missing

- One cross-repo quickstart with pinned versions and expected outputs.
- A version/compatibility matrix.
- A single contract/schema index with failure semantics.
- A clear separation between a synthetic contract demonstration and a real
  watershed analysis.
- Executable docs checks for links and command snippets.
- A plain-language explanation of what WS4 owns versus what FHOPS owns.

## Scope

- Audit the existing docs and record every gap with an owner.
- Publish a pinned cross-repo quickstart using committed synthetic fixtures.
- Publish a contract/schema index and failure matrix.
- Add executable docs checks.
- Record real-data and hydrologist-review blockers.
- Close out with explicit limits.

## Out of scope

- A new flood model, response surface, or watershed pilot.
- New data acquisition.
- Solver-side hydrology optimization.
- Rewriting FEMIC/WS4 reference material outside its owning repository.
- A claim that the system is operational or regulatory.

## User journey the docs must support

1. Install pinned FEMIC, WS4, and FHOPS versions.
2. Validate a synthetic FEMIC hydrology bundle.
3. Register it in WS4, map a crosswalk, and run a screening path.
4. Register it in FHOPS, map support, load exposure, screen a schedule.
5. Run the P16 hazard/asset/constraint-check path.
6. Understand which steps are synthetic and which need real data or review.

## P18.1 audit

The detailed gap matrix is `notes/p18_hydrology_docs_audit.md`. Summary: the
individual producer and consumer references exist, but the cross-repo quickstart,
version matrix, contract index, expected outputs, and executable docs checks do
not. Real watershed work remains blocked by data and review, not by missing docs.

## Tasks

- P18.1: documentation and reproducibility audit.
- P18.2: pinned cross-repo quickstart and version matrix.
- P18.3: contract/schema index and failure matrix.
- P18.4: executable docs checks.
- P18.5: closeout.

## Acceptance

- The audit names every gap and owner.
- The quickstart is copyable and its expected outputs are recorded.
- The contract index covers every schema used by the workflow.
- The compatibility matrix is explicit.
- Docs checks run in CI.
- The closeout states that synthetic contract demonstrations are not real
  watershed results.
