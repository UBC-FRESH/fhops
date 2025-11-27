FHOPS exposes the same metaheuristics benchmarked in the manuscript:

- **Simulated annealing** remains the default baseline (`bench suite` uses it unless disabled). The manuscript cites both the balanced preset (general-purpose) and the mobilisation preset (escapes landing-cap traps). Operator weights ship in `profiles.py`, so the exporter can surface them in the shared table.
- **Iterated local search** is included to show deterministic improvement over SA in short horizons (e.g., tiny7). The solver piggybacks on SA assignments when `--include-ils` is passed, reinforcing that end-users can reuse telemetry outputs.
- **Tabu search** demonstrates diversification on synthetic bundles: objective traces show convergence parity with SA but at lower runtime. The manuscript will highlight how automatic tenure selection removes another tuning burden.

These notes accompany the shared `heuristics_matrix.csv` so both the PDF and Sphinx docs can present identical solver guidance.
