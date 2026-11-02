# Per-machine fleet spec editing

Issue: #354. Branch: `issue-354-machine-specs`.

## Changes

- Core accepts `loader_specs` keyed by machine id; primary `loader_spec` remains
  the fallback.
- CLI adds `--loader-specs` and `--skidder-specs` JSON mappings; processor specs
  now preserve `per_log_s`.
- Studio machine records can carry a `spec` object. The machine-spec panel edits:
  - loader fixed/per-log process time;
  - processor seconds/m³, fixed setup, per-log time;
  - skidder payload, empty/loaded speeds, load/unload fixed and per-log times.
- Studio writes spec mappings into `system_args`; derived cases persist them.
- Tree Lab runner writes `loader_specs.json`, `skidder_specs.json`, and
  `processor_specs.json` inputs and passes the matching CLI flags.
- Blank fields continue to use scenario/default machine specifications.

## Verification

- Manifest test asserts loader/processor spec propagation.
- End-to-end derived run with `H4-B` loader and `H5-B` processor specs completed;
  both spec JSON inputs were written.
- 35 targeted tests pass; `ruff`, `mypy`, `node --check`, and `pre-commit` pass.

## Limits

- Truck capacity/cycle remain global.
- Spec overrides are numeric reference-model parameters, not field calibration.

## Closeout

- PR #355 merged to `main` as `9bf15c08176b4771d4be038763628070e65ce628`.
- Main CI `41487343948` passed.
- Public demo deployment: `032315cf`.
- Live Studio showed 4 spec groups / 19 fields with no page errors.
