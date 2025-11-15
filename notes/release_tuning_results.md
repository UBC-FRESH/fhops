# Release RC Tuning Run — Summary (2025-11-16)

Command:
```
python scripts/run_tuning_benchmarks.py \
  --plan baseline-smoke \
  --out-dir tmp/release-tuning \
  --random-runs 2 --random-iters 300 \
  --grid-iters 300 --grid-batch-size 2 --grid-preset balanced \
  --bayes-trials 3 --bayes-iters 300 \
  --ils-runs 2 --ils-iters 350 \
  --tabu-runs 2 --tabu-iters 1500 \
  --summary-label release-rc \
  --max-workers 8
```

Comparison vs. CI baseline:

| Scenario        | Algorithm | Best (tuned) | Best (baseline) | Δ best | Notes |
|-----------------|-----------|--------------|-----------------|--------|-------|
| FHOPS MiniToy   | random    | 35.50        | -6.00           | +41.5  | Random benefited from higher iterations and mobilisation-aware operators |
| FHOPS MiniToy   | grid      | 15.50        | 9.00            | +6.5   | Balanced preset + batch=2 maintained gap |
| FHOPS MiniToy   | bayes     | 11.50        | -33.75          | +45.25 | TPE quickly closed gap |
| FHOPS Small21   | grid      | -10.77       | -53.13          | +42.36 | Short-tier budgets still limited; tuned runs improved objective |
| FHOPS Medium42  | grid      | -733.25      | -1086.99        | +353.75 | All tuners showed gains; Medium42 remains hardest |

Artifacts:
- `tmp/release-tuning/tuner_report.{csv,md}`
- `tmp/release-tuning/comparison.{csv,md}` (tuned vs. baseline)
- `tmp/release-tuning/summary.{csv,md}`
- History delta: `tmp/release-tuning/history_delta.{csv,md}`
- Extracted presets: `notes/release_tuned_presets.json`

Next actions:
- Publish summary to README/docs + dashboards.
- Evaluate tuned presets for inclusion in CLI defaults (optional).
