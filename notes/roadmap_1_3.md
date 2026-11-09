# FHOPS 1.3 planning and BC salvage source audit

Issue: #436
Date: 2026-11-09
Baseline: FHOPS 1.2.1 (`v1.2.1`, release workflow `42650062331`)

## Current state

- FHOPS 1.2.1 is published on PyPI/TestPyPI with GitHub release assets.
- Main suite: 1410 passed, 219 skipped at release prep.
- Scenario Studio, CTL/forwarder calibration, product mix, operator-policy
  effects, salvage shelf-life, FEMIC ground-support, and serious-game dual
  replay are all on `main`.
- The remaining roadmap items are either large architecture work, external
  data/source-gated work, or operational validation that needs practitioner
  input.

## BC salvage source audit

Question: can FHOPS add a BC-specific numeric salvage retention curve without
inventing coefficients?

Source reviewed:

- Lewis, K.J. and Hartley, I.D. (2006). *Rate of deterioration, degrade, and
  fall of trees killed by mountain pine beetle.* BC Journal of Ecosystems and
  Management 7(2):11-19. DOI:
  <https://doi.org/10.22230/jem.2006v7n2a538>.

What the source provides:

- A BC mountain-pine-beetle synthesis focused on lodgepole pine.
- Moisture-content, checking, bluestain, decay, and fall evidence.
- The finding that standing-pine decay is slow and fall often precedes
  substantial volume loss; once trees are on the ground, decay accelerates.
- Product-specific observations, including lumber recovery by deterioration
  class, veneer recovery differences, and Kraft/mechanical pulp property
  changes.

What it does **not** provide:

- a year-indexed net-volume retention series;
- a product-class retention or value-loss series;
- a species/product shelf-life table suitable for coding as numeric curve
  points.

Decision: **do not add a BC-specific `salvage.decay.v1` curve from this
source.** Doing so would require inventing a time/volume mapping. The existing
Prestemon & Holmes (2008) curve remains a US Pacific Northwest reference, and
the Barrette et al. (2015) product windows remain advisory.

A future BC/Canadian curve needs a source that publishes explicit retention or
recovery factors by year and product/species, plus a stated climate/storage
boundary. The Lewis & Hartley synthesis is still valuable as a qualitative
applicability note.

## Candidate 1.3 scopes

| Candidate | Value | Risk / prerequisite |
| --- | --- | --- |
| Data-quality inspector closure | Prevents GIGO in shipped scenarios | Needs agreement on enforcement vs. warning |
| BC/Canadian salvage curve | Higher-value dead-wood modelling | Blocked on a numeric public/project-approved source |
| Studio accessibility/performance | Better instructor/user experience | Needs browser profiling and UX review |
| Kernel adapter parity stabilization | Removes duplicate solver loops | Cross-repo coordination and performance gates |
| Cloud execution harness | Scale/automation | Infrastructure and security design |
| DSS/ArcGIS/QGIS hooks | External workflow integration | Partner requirements and API design |

## Recommended 1.3.0 slice

Recommended bounded scope: **“operational data quality and evidence intake.”**

1. Close the dataset-inspection roadmap:
   - make the 24 h/day machine-availability check explicit;
   - surface machine-role/ground-support mismatches;
   - keep warnings vs. errors documented and tested.
2. Add a salvage evidence intake check:
   - accept only curves with explicit year/product retention points;
   - document the BC MPB qualitative boundary alongside the existing curve;
   - add no new coefficients without a cited source.
3. Harden release/evidence outputs:
   - include schema versions and provenance in Studio comparison exports;
   - keep the trusted-publishing workflow and release checklist current.

Out of scope for 1.3.0 unless a source or partner requirement arrives:
new BC curves, roadside-storage decay, grade/value recovery, ws4 carbon-engine
changes, and cloud execution.

## Acceptance gates

- Full suite, ruff, mypy, pre-commit, Sphinx.
- No unsupported coefficients; every numeric dataset cites a public or
  project-approved source and boundary.
- Dataset warnings documented and covered by regression tests.
- Release artifacts and trusted-publishing workflow remain reproducible.

## Next action

Open child issues for the three candidate slices after maintainer selection;
do not start a BC curve until a numeric source is approved.
