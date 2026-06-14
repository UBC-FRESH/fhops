# v1.0.0 User-Facing Documentation Readiness Sweep

Date: 2026-06-14
Status: Active - issue #27, under the v1.0.0 GA release issue tree.

## Scope

This sweep checks the public documentation path a reviewer or first-time user is
likely to follow before the final v1.0.0 publication step:

- README installation and quickstart examples.
- Sphinx navigation, overview, quickstart, evaluation, CLI reference, and release notes.
- SoftwareX-facing README material that points to manuscript/reference-document assets.
- Release-facing language that could still imply an alpha/beta/pre-publication state.

## Findings Fixed In This Branch

- README rendering had a missing closing code fence in the development-install block,
  causing the optional Gurobi setup and following sections to render as code.
- README and quickstart examples used the old positional ``fhops evaluate`` schedule
  argument; the current CLI requires ``--assignments``.
- Several user-facing guides referred to ``fhops eval playback`` or ``fhops
  eval-playback --scenario``. The actual command is ``fhops eval-playback SCENARIO
  --assignments ...``.
- The Sphinx landing navigation opened the "Getting Started" section with live
  dashboards before overview/install/quickstart pages. Dashboards now live under the
  reference section.
- The overview and quickstart did not clearly distinguish between installed package
  contents and source-checkout example paths. The docs now state that PyPI installs the
  CLI/package/runtime data, while ``examples/`` and ``tests/fixtures/`` come from the
  source repository.
- v1.0.0 release notes still listed already-closed release-prep issues #17-#19 as
  future work. They now point only to this docs sweep and final publication issue #20.
- The SoftwareX workspace README still described a public ``reference/`` directory that
  was moved into the private ``reference-documents`` submodule.
- Historical alpha release-note pages now carry a short warning that new users should use
  the v1.0.0 release notes and ``pip install fhops==1.0.0``.

## Deferred Follow-Ups

- Old planning notes still contain historical paths under ``docs/softwarex/reference/``.
  They are not on the primary user path and should be cleaned during a post-submission
  manuscript/provenance-note tidy rather than blocking v1.0.0.
- The CLI reference remains hand-written. A future docs improvement should generate it
  from Typer help output or add a CI check that validates documented commands against
  the current command tree.
