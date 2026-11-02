# Per-landing processor/loader fleets

Issue: #346. Branch: `issue-346-landing-fleets`.

## Changes

- Public `LandingFleet(landing_id, loader_machine_id, processor_machine_ids)`.
- `fhops tree system` accepts repeatable:
  - `--landing-loader landing_id:machine_id`
  - `--landing-processor landing_id:machine_id`
- Each landing can use a dedicated loader and processor set.
- Processor stages run independently per landing fleet.
- Loader scheduling is per loader machine, with truck stockpiles still tracked
  per landing.
- Studio machine rows have a landing selector for loaders/processors.
- Fleet-clone machines (`H4-B`, `H5-B`, …) are available in the catalog.
- Derived cases append clone machine and calendar rows so the runner can
  instantiate them.
- Run output includes all fleet loaders/processors in machine summaries and
  provenance.

## Verification

- Core test with a second loader (`H7`) and separate processor fleets checks
  processing/loading events across both landings.
- Derived-case test checks `landing_fleets`, clone machine rows, and calendar
  rows.
- End-to-end derived-case run completed with machine summaries for
  `H4`, `H4-B`, `H5`, and `H5-B`.
- 34 targeted tests passed; `ruff`, `mypy`, `node --check`, and `pre-commit`
  pass.

## Limits

- Clone machines use the base machine templates and default rates.
- Truck fleet remains shared; per-landing truck fleets are a future extension.
- If a landing has processors but no loader, configuration validation rejects it.
