# Studio run freshness and stale-run UX

Issue: #334. Branch: `issue-334-run-freshness`.

## Problem

Studio projects can change terrain, retention, machines, or operator policies
after a run. The replay still uses the old scene and can look current. After the
terrain-elevation fix this became especially confusing because old runs keep
their old elevations.

## Design

Run-affecting edits are hashed into two stable signatures:

- `project_edit_signature`: boundary, landing, road, retention, machines,
  operator policies, and terrain. Derived `system_args` are excluded because
  they are regenerated from those inputs.
- `terrain_signature`: the terrain mapping separately, so the UI can say
  specifically that terrain changed.

`materialize_case` writes `studio_project_revision`,
`studio_project_updated_utc`, `studio_edit_signature`, and
`studio_terrain_signature` into the derived case manifest. `run_case` copies
these into a `studio` block in `run.json`.

`run_freshness(project, run_record)` compares signatures:

- identical: fresh;
- terrain differs: stale with a terrain reason;
- other edit differs: stale with a project-edit reason;
- legacy run without signatures: stale and explicitly marked legacy.

## UX

- Run history shows a **stale** badge, tooltip reasons, and a **Rerun** action.
- Replay shows a top stale banner with reasons and a **Rerun project** button.
  The button creates a new run and redirects to it.
- Existing runs remain visible and downloadable; they are not deleted.

## Tests

- `test_project_signatures_detect_run_affecting_changes`
- `test_materialized_case_carries_project_signatures`
- `test_run_history_marks_stale_after_project_edit`
- API smoke tests and existing Studio/replay tests.

## Notes

- Label, notes, timestamps, and revision alone do not invalidate a run.
- A rerun generates a new run id; prior run artifacts remain immutable.
- Old runs created before this change are marked legacy/stale and need a rerun
  to pick up current project edits.

## Closeout

- PR #335 merged to `main` as `c63b80cf92a24bbf03f50686d045298b3657d95c`.
- Main CI `41368063201` passed.
- Public demo deployment: `de28b0d9`.
- Live checks: legacy run shows the stale banner; fresh run
  `20261102T003731Z` is fresh; run history shows stale badges and rerun actions.
