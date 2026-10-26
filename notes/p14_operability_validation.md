# P14.4 operability validation

Date: 2026-10-26
Issue: #192 (P14.4)
Evidence commit: added with the P14.4 PR.

## Scope

P14.4 adds an **advisory** operability classifier. It reads the block/landing `lidar_support` rows,
classifies terrain as ground/cable/helicopter with visible assumptions and fallbacks, compares the
scenario's current harvest system, recommends a class-compatible system, and exposes labelled
move-in/landing/road cost context. It does not rewrite systems or apply cost multipliers in the
solver.

## Smoke validation

A copy of `examples/tiny7` was given two synthetic block support rows:

- B01: slope 45%, roughness 0.20 m, canopy 60% -> **cable**;
- B02: slope 8%, roughness 0.10 m -> **ground**.

`fhops scenario lidar operability ... --json` reported B01 as cable (current
`ground_fb_skid` incompatible, recommended `cable_running_tr122_clearcut`) and B02 as ground
(current system compatible).

The same scenario solved with the heuristic CLI:

```bash
fhops solve-heur /tmp/opencode/p14-operability/tiny7/scenario.yaml \
  --iters 20 --seed 7 \
  --out /tmp/opencode/p14-operability/assignments.csv \
  --telemetry-log /tmp/opencode/p14-operability/telemetry.jsonl
```

Result: objective 4295.775, total production 4414.703 m³, 0 sequencing violations, assignments
written. This confirms the advisory evidence does not break the existing solver path; it does not
claim that the solver chose the recommended system. The CLI report is the integration point for
P14.5/P14.6.

## Assumptions and limits

- Thresholds are planning assumptions: ground <=35% slope and <=0.35 m roughness; cable up to 60%
  and 0.55 m; above that is helicopter. They are not field-validated.
- Aspect is reported but does not change the class yet.
- Cost multipliers are advisory context, not applied to machine/move-in/landing/road cost models.
- No individual-tree segmentation or financial feasibility claim is made.
