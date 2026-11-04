# P45 close-out: FHOPS ground-summary support report

Phase: P45 FHOPS ground-summary support report
Parent issue: #422
Child issue: #423
Branch: `feature/p45-ground-summary-support`
Date: 2026-11-04
Status: complete; read-only consumer

## Summary

FHOPS can now inspect a FEMIC `femic.ground-summary.v1` CSV against a scenario:

```bash
fhops scenario lidar ground-summary \
  examples/lidar_tfl6/scenario.yaml \
  runtime/p135/tfl6_blocks_summary.csv \
  --json
```

The report lists matched block rows with point count, ground fraction, low-point fraction,
HAG mean, and HAG p95. It also lists scenario blocks without a summary and summary blocks
that are not in the scenario.

It is read-only: it does not write the scenario, change `lidar_support`, or change the
solver.

## Evidence

- Unit and CLI tests: 5 passed.
- Real TFL6 summary: 7 rows, zero missing blocks, zero unknown blocks, no warnings.
- The reader accepts `block_id` and `polygon_id` identifier columns.
- Bad columns, fractions, counts, and duplicates fail clearly.
- Sphinx docs build with warnings as errors.

## Limits

- Ground fractions are point composition, not area or accuracy.
- The report does not apply ground evidence to an objective or constraint.
- A scenario schema field for ground support remains a separate decision.

## Verification

- `PYTHONPATH=src python -m pytest tests/scenario/test_lidar_ground_summary.py -q`
- `ruff check src/fhops/scenario/lidar_ground_summary.py tests/scenario/test_lidar_ground_summary.py`
- `mypy src/fhops/scenario/lidar_ground_summary.py`
- `sphinx-build -b html docs _build/html -W`
