# v1.0.0 Release Surface Audit

Date: 2026-06-14
Status: Active - issue #19, under the v1.0.0 GA release issue tree.

## Scope

This note tracks the public surfaces that could make the FHOPS v1.0.0 release look stale,
accidental, or still prerelease-only to SoftwareX reviewers and users.

## Findings

- GitHub's latest stable release currently resolves to `v0.0.2`, published 2025-11-10.
- `v0.0.1-alpha3` is a newer GitHub prerelease, published 2026-04-17 from `main`, but the
  tagged source still reports `fhops.__version__ = "1.0.0a2"`. Its release notes compare
  `v1.0.0-alpha2...v0.0.1-alpha3`, which makes it look like a confused prerelease rather
  than a stable milestone.
- The `v0.0.1-alpha3` tag and a 2026-06-14 manual `workflow_dispatch` run both exposed the
  same release-build failure: the workflow called `hatch run release:build`, but `hatch build`
  cannot run inside a normal Hatch environment. The workflow should call `hatch clean &&
  hatch build` directly, matching the release playbook and successful local artifact-smoke
  commands.
- After correcting the workflow command on `issue-19-release-surface-audit`, manual
  `Release Build Verification` run `27512093324` succeeded and uploaded `dist/` artifacts.
- GitHub Pages is in workflow deployment mode and serves `https://ubc-fresh.github.io/fhops/`.
  The Pages API still reports `feature/towards-phase3-milestone` as its stored source
  branch, but current CI deploys the Pages artifact from `main` only through the
  `deploy-pages` action.
- The weekly `Analytics Notebooks (Full)` workflow has repeated scheduled failures on
  `main`; the last visible failure reached `Execute analytics notebooks (full)` and then
  failed at `Collect notebook artefacts`. GitHub's detailed logs for that February 2026 run
  have expired, so the exact shell line cannot be recovered.

## Decisions

- Keep `v0.0.1-alpha3` in place instead of deleting the tag or release before GA. It is a
  prerelease, not the latest stable release, and deleting historical release artifacts
  creates avoidable provenance churn during manuscript submission. Add a public release
  note annotation that it is superseded by the v1.0.0 GA path.
- Treat the stale Pages source branch as non-blocking while Pages remains in workflow
  deployment mode. The release blocker is the actual deployed artifact from `main`, not the
  legacy source-field label.
- Harden the full analytics artifact collection step now, then treat a fresh manual full
  analytics run as the release readiness check. A failed full analytics run should not block
  PyPI publication if the standard CI light notebooks and Sphinx build pass, but it should
  block any claim that the telemetry dashboards are freshly regenerated.

## Release-Day Checklist

- [x] Confirm a manual `Release Build Verification` workflow run succeeds after the workflow
  command is corrected.
- [ ] Re-run or confirm `Release Build Verification` on `main` after this branch merges and
  before the signed `v1.0.0` tag is created.
- [ ] Confirm the current `main` CI run succeeds and deploys the Pages artifact.
- [ ] Trigger `Analytics Notebooks (Full)` manually after this workflow hardening lands; if it
  fails again, open a follow-up with the fresh run URL and exclude "fresh full dashboard
  refresh" from the v1.0.0 claims.
- [ ] Confirm the GitHub release created for `v1.0.0` is non-prerelease and becomes the latest
  stable GitHub release.
- [ ] Confirm PyPI serves `fhops==1.0.0` and that the install snippet in README/docs matches
  the published package.
