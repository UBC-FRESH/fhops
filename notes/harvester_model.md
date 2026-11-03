# Harvester-specific processing model

Issue: #386. Branch: `feature/p45-harvester-economics-cleanup`.

## Change

`simulate_block` now accepts `processing_model`:

- `feller_buncher` keeps the whole-tree reference assumption;
- `harvester` uses the tree’s bucked log count and mean log length in the
  ADV6N10 CTL harvester regression, approximating stump-side multi-product
  bucking.

`simulate_ground_system` selects the model from the scenario machine role:
`harvester` → harvester, otherwise feller-buncher. Run provenance records the
machine, scenario role, selected model, and citation text, and the caveat text is
role-specific.

## Verification

- Spatial-machine test confirms the two models produce different processing
  times while preserving log counts.
- Ground-system test changes H1 to `harvester` and checks provenance/caveat.
- CTL replay machine labels remain harvester/forwarder/loader.

## Limits

- The harvester model still uses the reference ADV6N10 regression and reference
  stem bucking; it is not a new field-calibrated harvester study.
- The feller-buncher model remains the legacy whole-tree assumption.
