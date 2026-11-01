# 3D replay UI — retention visibility and timeline

Issue: #330. Branch: `issue-330-replay-timeline`.

## Problem

The Studio replay was already passing retained-tree payloads to the viewer, but
the teal crowns were small, dark, and frequently occluded by the harvested
stand. At normal replay zoom users mostly saw the thin teal markers, not the
retained trees. The replay also had only the scrub slider, with no machine-event
timeline.

## Changes

- Retained and stream-buffer trees now render as bright teal crowns with a
  ground ring and a taller beacon. The crowns and markers render over the
  harvested stand so retention is readable at normal zoom; this is deliberately
  an authoring/QA overlay rather than a physical canopy render.
- Retention clumps are more visible, riparian clumps use blue, and each clump
  gets a floating label.
- The replay HUD has a retained/riparian and stream-buffer legend.
- The replay controls now include a **Timeline** button.
  - The timeline panel shows one lane per machine.
  - Event bars use machine-event colors.
  - A mouse-positionable cursor head shows the hovered time.
  - Clicking or dragging the timeline seeks the replay.
  - The cursor tracks playback when the mouse is not over the panel.

## Verification

- 2D and 3D editor stream-buffer tests remain green.
- Manual browser smoke test with the Gavin demo replay at
  `build/studio_projects/afrf-gavin-20261101t001939-6828`:
  - retained cluster visible as teal trees and rings;
  - legend visible;
  - timeline opens from the controls;
  - hover cursor reports the hovered time;
  - click/drag seeks the replay status and machine state.
- `node --check` passes for `studio_replay.js` and `viewer.js`.
- `pytest -q tests/studio/test_studio_app.py tests/studio/test_studio_projects.py tests/tree/test_ground_system.py` — 24 passed.
- `ruff check`, `ruff format --check`, `mypy src`, and `pre-commit` pass.

## Limits

- The retained-tree overlay renders through canopy/terrain so it can be used for
  retention QA. A future “physical occlusion” toggle can restore strict depth
  testing.
- Timeline events are read-only; editing machine schedules is out of scope.
