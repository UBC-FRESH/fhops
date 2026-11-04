# Operator-policy effects integration

Issue: #391. Branch: `issue-391-policy-effects`.

## Changes

- Studio computes and displays per-machine policy effects:
  - cycle multiplier,
  - breakdown risk,
  - break policy,
  - grade caution,
  - damage risk and its product-recovery downgrade.
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
- Damage risk derives a sawlog-to-pulp downgrade fraction averaged across
  machines: low/normal 0%, elevated 5%, high 10%. The fraction is passed as
  `--damage-downgrade-fraction`, recorded in run provenance, and applied to
  product mix, revenue, and net margin. Steady policies therefore leave the
  CTL product mix unchanged.

## Verification

- Operator-policy test asserts cycle, breakdown, grade, damage, and failure settings.
- Studio policy-effects panel renders from the project dataset.
- Core test asserts the 10% downgrade moves volume from sawlog to pulp and records
  provenance.
- 46 targeted tests pass; full local pytest has only the two pre-existing HiGHS
  option-error assertions (1360 passed, 214 skipped).

## Demo evidence

A duplicate of the CTL project with all machines on the throughput preset (5%
downgrade), project `afrf-gavin-20261104t010235-3dfa`, run
`20261104T010235Z`:

| Metric | Steady CTL | Throughput policy |
|---|---:|---:|
| Sawlog / pulp m³ | 772.8 / 3.2 | 734.2 / 41.9 |
| Downgraded sawlog m³ | 0.0 | 38.6 |
| Product revenue | $65,804 | $63,872 |
| Total cost | $13,489 | $18,064 |
| Net margin | $52,314 | $45,807 |
| Makespan | 20.3 h | 27.3 h |

The demo link combines the downgrade with the throughput preset's other effects
(cycle, grade, and breakdown risk); it is not an isolated damage-only trial.

## Limits

- The damage adjustment is a product-recovery assumption, not a physical
  tree-damage or mill-grade model; it reclassifies sawlog volume rather than
  creating or destroying fibre.
- Break policy affects stochastic failure rate rather than explicit scheduled
  breaks.
