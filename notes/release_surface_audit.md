# v1.0.0 Release Surface Audit

Date: 2026-06-14
Status: Complete - issue #19 closed, with final release-surface verification completed
under issue #20 on 2026-06-15.

## Scope

This note tracked the public surfaces that could make the FHOPS v1.0.0 release look stale,
accidental, or still prerelease-only to SoftwareX reviewers and users. The final release
surface is now stable: PyPI/TestPyPI serve `fhops==1.0.0`, the public GitHub release is
non-prerelease, and the tag-triggered release-build workflow passed.

## Findings

- Before GA publication, GitHub's latest stable release resolved to `v0.0.2`, published
  2025-11-10.
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

## Final Outcome

- `v1.0.0` was published on 2026-06-15 from `main` commit
  `d98fd104e69686ba4498d6628b646f210d7b9af1`.
- PyPI and TestPyPI both report `fhops` latest as `1.0.0`, and clean install smoke tests
  from both indexes printed `fhops.__version__ == "1.0.0"`.
- The GitHub release `FHOPS v1.0.0` is public, non-draft, and non-prerelease.
- The tag-triggered `Release Build Verification` workflow passed in run `27517181902`.
- The `v1.0.0` tag is annotated rather than GPG-signed because the release environment
  had no GPG secret key or signing configuration available.

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
- [x] Re-run or confirm `Release Build Verification` on `main` after this branch merges and
  before the annotated `v1.0.0` tag is created.
- [x] Confirm the current `main` CI run succeeds and deploys the Pages artifact.
- [ ] Trigger `Analytics Notebooks (Full)` manually after this workflow hardening lands; if it
  fails again, open a follow-up with the fresh run URL and exclude "fresh full dashboard
  refresh" from the v1.0.0 claims.
- [x] Confirm the GitHub release created for `v1.0.0` is non-prerelease and becomes the latest
  stable GitHub release.
- [x] Confirm PyPI serves `fhops==1.0.0` and that the install snippet in README/docs matches
  the published package.
