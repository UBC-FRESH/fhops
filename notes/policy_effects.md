# Operator-policy effects integration

Issue: #391. Branch: `issue-391-policy-effects`.

## Changes

- Studio computes and displays per-machine policy effects:
  - cycle multiplier,
  - breakdown risk,
  - break policy,
  - grade caution,
  - damage risk (advisory).
- `apply_operator_policies` stores `system_args.policy_effects` and an aggregate
  run summary.
- Non-steady policies now derive stochastic breakdown assumptions when
  `shift_days` is present:
  - failure rate from breakdown risk and break policy,
  - repair hours,
  - repair CV and deterministic seed.
- The Tree Lab runner passes `--failure-rate`, `--repair-hours`,
  `--repair-cv`, and `--breakdown-seed` when present.
- Grade caution derives a run grade limit: high caution caps at 80%, relaxed
  raises to at least 150%. Existing terrain limits remain the baseline.

## Verification

- Operator-policy test asserts cycle, breakdown, grade, and failure settings.
- Studio policy-effects panel renders from the project dataset.
- 45 targeted tests pass.

## Limits

- Damage risk remains advisory; it is not a physical tree-damage model.
- Break policy affects stochastic failure rate rather than explicit scheduled
  breaks.
