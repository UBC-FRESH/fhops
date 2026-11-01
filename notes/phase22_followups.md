# Phase 22 — Scenario Studio follow-ups

Parent issue: #324. Children: #325, #326. Branch: `feature/p22-scenario-followups`.
Status: active.

## Scope

Close the remaining Phase 21 follow-ups without changing host routing or the
immutable Tree Lab cases:

- processor-specific operator-policy coefficients;
- stream-centreline authoring that generates riparian retention clumps;
- closeout documentation corrections and public-demo sync.

## Decisions

- Processor policy coefficients flow through one explicit
  `processor_productivity_multiplier` in the core system runner and CLI. This
  keeps provenance visible and lets the Studio translate per-machine policy
  presets without introducing a second processor model.
- Stream buffers are authoring geometry. A drawn centreline and width become a
  `riparian` retention clump, so the existing tree-filtering, felling, routing,
  and obstacle rules apply unchanged.
- The Studio still writes only `build/studio_projects`; `sandbox/cases` remains
  immutable.

## Implementation notes

### Processor policies

- `fhops.ground_system.simulate_ground_system` accepts
  `processor_productivity_multiplier` (default `1.0`, must be positive and
  finite). It scales fixed, per-cubic-metre, and per-log processor time.
- `fhops tree system --processor-productivity-multiplier` exposes the control.
- `sandbox.studio.projects.apply_operator_policies` derives the multiplier from
  the selected processor policy presets and stores it in `system_args`.
- The multiplier is recorded under `rate_provenance.processor`.

### Stream buffers

- `sandbox.studio.projects.stream_buffer_polygon` offsets a centreline by half
  the requested width and returns a closed ring.
- `POST /api/geometry/stream-buffer` exposes the helper to the 2D and 3D editors.
- The Stream tool draws a centreline; double-click creates a `riparian` clump
  with `source: "stream"`, `buffer_m`, `centerline`, and `polygon`.
- Riparian clumps render blue in 2D, 3D editing, and replay; they retain trees,
  exclude felling, and block machine routes through the normal clump path.

## Tests

- `tests/tree/test_ground_system.py` covers multiplier scaling, provenance, and
  non-positive rejection.
- `tests/studio/test_studio_projects.py` covers processor policy translation and
  stream-buffer area/extent.

## Verification commands

```bash
ruff format src tests sandbox
ruff check src tests sandbox
mypy src
pytest -q tests/tree/test_ground_system.py tests/studio/test_studio_projects.py
node --check sandbox/studio/static/studio.js
node --check sandbox/studio/static/studio_3d.js
python -m py_compile sandbox/studio/app.py sandbox/studio/projects.py
pre-commit run --all-files
```

Full `pytest` still fails only the two pre-existing HiGHS option-error
assertions:

- `tests/model/test_milp_driver_robustness.py::test_highs_option_error_is_reported_as_solver_error`
- `tests/test_legacy_mip_driver.py::test_highs_option_error_is_reported_as_solver_error[highs-exec]`

Sphinx remains blocked locally by missing Pandoc (Phase 21 closeout).

## Closeout

- Update `ROADMAP.md`, `CHANGE_LOG.md`, and this note.
- Record CI results on the phase PR.
- Do not merge, tag, or change settings without explicit approval.
