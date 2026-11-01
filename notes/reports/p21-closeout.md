# Phase 21 closeout report — Scenario Studio

Parent issue: #318  
Children: #319, #320, #321, #322  
Branch: `feature/p21-demo-integration` (pushed to origin)  
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
- No CI run exists for the pushed phase branch.

## Deviations requiring approval

1. The phase branch is based on the public-demo line, not `main`. A clean PR would need either:
   - approval to use the public-demo base, or
   - a clean branch reconstructed from `main` with only the Studio work.
2. The implementation preceded issue creation (#318–#322); the issue tree now exists and this deviation is recorded.
3. No phase pull request or per-child PR was opened.
4. Full repository gates remain blocked by the environment/pre-existing test issues above.

## Decision requested

The maintainer should choose the base and approve the PR path. No merge, tag, release, or settings change has been performed.

## Live deployment

The public demo checkout was updated under commit `22d6b439`; this is a deployment action and does not alter the phase branch history.
