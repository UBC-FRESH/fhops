# Studio salvage-age overlay

Issue: #418.

## Change

Studio projects now carry an optional read-only salvage configuration:

```json
"salvage": {
  "curve_id": "pnw_fire_killed_mixed_conifer",
  "ages": {"AFRF_GAVIN_485": 2.0}
}
```

The Machines/run sidebar has a **Salvage shelf-life** panel:

- set `years_since_disturbance` for the project block;
- preview retention, retained volume, eligible products, source, and boundary;
- clear the age;
- save the project to persist the age.

The preview calls `POST /api/projects/<id>/salvage`, which uses the existing
`fhops.salvage` report consumer and the project's immutable base scenario. It
does not change run KPIs, scheduling, truck loading, machine assignment,
economics, or replay.

Existing projects load with an empty age map; saving normalizes the field.

## Exports

- Project export includes `salvage` because it is part of the project JSON.
- Comparison JSON includes each side's `salvage` configuration.

## Validation

- Ages must be finite and non-negative.
- `block_id` joins preserve strings inside the report consumer.
- Unknown blocks/curves return a client error.
- The panel labels the report as reference-only and notes when the block has no
  `salvage_processing_mode`.

## Verification

- Project tests: default/legacy normalization and invalid-age rejection.
- API test: configured and empty previews, invalid age, unknown curve.
- Browser smoke on the Gavin project: age 2 → 0.89 retention, 1,206.8 m³
  retained; save persisted the age; clear + save removed it; no page errors.
- Full `pytest`: 1391 passed, 219 skipped; Sphinx `-W`: clean.

## Limits

- The overlay is a reference preview, not a schedule.
- The curve remains the P44 US Pacific Northwest reference; BC/species curves
  need their own reviewed source.
- Optional retained value is not part of the Studio overlay; the CLI report
  retains that caller-supplied option.
