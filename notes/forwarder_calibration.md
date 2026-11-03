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

## Limits

- The productivity value is a scalar calibrated at a reference distance, not a
  distance-varying regression inside the event model.
- Forwarder loading/unloading split is still reference timing.
