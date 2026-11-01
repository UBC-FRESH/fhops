# Phase 21 closeout report — Scenario Studio

Parent issue: #318
Children: #319, #320, #321, #322
Branch: `feature/p21-demo-integration` (pushed to origin)
Pull request: #323
Report date: 2026-11-01

## Delivered

- Project schema, persistence, import/export, duplication, and immutable base-case references.
- 2D editor for boundary, landing, road, retention, terrain, machines, and operator policies.
- 3D editor for orbit, landing, retention, terrain, road, boundary, undo/redo, rename, duplicate, run, and replay.
- Retention clumps and presets (retention, riparian, corridor) with tree exclusion and route blocking.
- Terrain heightfield/DEM handoff, access-map overlay, terrain-aware core routes, persisted replay paths, and blocked-route warnings.
- Operator-policy translation for feller, skidder, loader, and grade caution.
- Derived-case runs, KPI result panels, run comparison, run history, and Tree Lab promotion.
- Public demo deployment under `/studio/`, `/studio/3d`, and `/studio/replay`.

## Verification

Passing:

- `ruff check .`
- `ruff format --check .`
- `mypy src` — 188 source files
- `python -m pre_commit run --all-files`
- `pytest -q tests/studio/test_studio_projects.py tests/tree/test_ground_system_terrain.py`
- Local/public Studio route checks: `/studio/`, `/studio/3d`, `/studio/replay`, `/studio/api/health`
- Playwright 3D editor and 3D replay smoke tests

Not passing / not run:

- Full `pytest` stops at the pre-existing HiGHS `iteration_count` option-error assertion in `tests/model/test_milp_driver_robustness.py`; unrelated to Phase 21.
- Sphinx cannot complete because Pandoc is unavailable (`nbsphinx.NotebookError: PandocMissing`).
- CI on PR #323 was green at `83288bad` (runs 41274821255 and 41274824233) and again at the final head `e34628aa` (runs 41275784979 and 41275788712). Main CI run `41276592250` passed after merge.

## Deviations and resolution

1. The original feature branch was based on the public-demo line. This was resolved by reconstructing a clean `feature/p21-demo-integration` branch from `main` and porting only the game, sandbox/Tree Lab, Studio, tests, and documentation.
2. The implementation preceded issue creation (#318–#322); the issue tree was created and linked, and the deviation is recorded.
3. The phase was delivered as one PR (#323) rather than child PRs, with the child issues closed against the merged phase record.
4. Full local repository gates remain blocked by the pre-existing HiGHS `iteration_count` assertion and missing Pandoc noted above. CI passed on the same tree.

## Outcome

PR #323 was squash-merged into `main` as `e16582b2e9ba71721e9ef1bc2d001f66599ea17d`.
Phase and child issues #318–#322 are closed. No tag, release, host networking,
or settings change was part of this phase.

## Live deployment

The public demo checkout was updated under commit `22d6b439`; this is a deployment action and does not alter the phase branch history.
