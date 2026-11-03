# Calibrated forwarder productivity

Issue: #371. Branch: `issue-371-forwarder-calibration`.

## Change

`MachineSpec.productivity_m3_per_smh` provides a calibrated forwarder
productivity value. When set on a forwarder machine, the cycle time is:

```text
cycle_seconds = bunch_volume_m3 / productivity_m3_per_smh * 3600
```

Travel time is still sampled from the assigned route and forwarder speeds; the
remaining cycle time is split between loading and unloading. This avoids using
the Han grapple-skidder whole-tree regression for CTL forwarders.

## Wiring

- CLI `--skidder-specs` accepts `productivity_m3_per_smh`.
- Studio forwarder/skidder spec editor exposes the field.
- Derived cases and runner already pass `skidder_specs.json`.
- Reference value for the CTL demo: Eriksson & Lindroos (2014) final-felling,
  350 m extraction, 0.3 m³ stems, 16 m³ load → **22.87 m³/PMH**.

## Verification

- Core test compares 2 vs 20 m³/SMH forwarders and checks makespan ordering.
- 37 targeted tests pass; `ruff`, `mypy`, `node --check`, and `pre-commit` pass.

## Distance-varying regression

- `MachineSpec.forwarder_model` accepts `eriksson-final-felling`,
  `eriksson-thinning`, `adv1n12-shortwood`, `ghaffariyan-small`, or
  `ghaffariyan-large`.
- The helper is evaluated with each bunch’s actual route distance; Eriksson
  models additionally use `forwarder_stem_size_m3` and payload capacity.
- `productivity_m3_per_smh` remains the scalar fallback.
- Studio exposes the model and stem-size fields; runner writes them in
  `skidder_specs.json`.

## Forwarder load/unload timing

- Optional `forwarder_load_fixed_s`, `forwarder_load_per_log_s`,
  `forwarder_unload_fixed_s`, and `forwarder_unload_per_log_s` fields define the
  split of the calibrated cycle residual.
- The residual is divided in proportion to the configured load/unload timings;
  if no timings are configured, the legacy 50/50 split is retained.
- Studio and skidder-spec JSON expose all four fields.

## Limits

- Supported models are limited to those with extraction-distance inputs; Kellogg
  and brushwood models require additional inputs and are not wired.
