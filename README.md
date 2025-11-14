# FHOPS — Forest Harvesting Operations Planning System

FHOPS is a Python package and CLI for building, solving, and evaluating
forest harvesting operations plans. It provides:
- A **data contract** (Pydantic models) for blocks, machines, landings, calendars.
- A **deterministic MIP** builder using **Pyomo**, with **HiGHS** as the default solver (optional **Gurobi** support when installed/licensed).
- A **metaheuristic engine** (Simulated Annealing v0.1) with pluggable operators.
- A CLI (`fhops`) to validate data, solve with MIP or heuristics, and evaluate results.

## Quick start (development install)

```bash
# inside a fresh virtual environment (Python 3.12+ recommended)
pip install -e .[dev]
# optional extras for spatial IO
pip install .[geo]
# optional extras for commercial MIP backends
# (requires a Gurobi install + license)
pip install .[gurobi]

### Optional: Gurobi setup (Linux)

HiGHS remains the default open-source MIP solver. If you have an academic or commercial Gurobi
licence and want to use it with FHOPS:

```bash
# install gurobipy alongside FHOPS
pip install fhops[gurobi]

# download the licence tools bundle (version shown as example)
wget https://packages.gurobi.com/lictools/licensetools13.0.0_linux64.tar.gz
tar xvfz licensetools13.0.0_linux64.tar.gz

# request your licence key (replace XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX)
./grbgetkey XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

# accept the default install path (typically $HOME/gurobi.lic) or specify a custom location.
# if stored elsewhere, point gurobipy at it:
export GRB_LICENSE_FILE=/path/to/gurobi.lic

# quick sanity check
python -c "import gurobipy as gp; m = gp.Model(); m.setParam('OutputFlag', 0); m.optimize()"
```

After the licence is active you can run FHOPS MIP commands with ``--driver gurobi`` (or
``gurobi-appsi`` / ``gurobi-direct``). Without an available licence FHOPS falls back to HiGHS.

# Validate and solve the tiny example:
fhops validate examples/minitoy/scenario.yaml
fhops solve-mip examples/minitoy/scenario.yaml --out examples/minitoy/out/mip_solution.csv
fhops solve-heur examples/minitoy/scenario.yaml --out examples/minitoy/out/sa_solution.csv
fhops evaluate examples/minitoy/scenario.yaml examples/minitoy/out/mip_solution.csv

# Exercise the regression baseline (sequencing + mobilisation setup checks)
fhops solve-mip tests/fixtures/regression/regression.yaml --out /tmp/regression_mip.csv
fhops solve-heur tests/fixtures/regression/regression.yaml --out /tmp/regression_sa.csv
fhops evaluate tests/fixtures/regression/regression.yaml /tmp/regression_sa.csv
# Expected evaluation output includes `sequencing_violation_count=0`. Mobilisation costs are
# exercised in `tests/test_regression_integration.py`, which injects machine parameters before
# running the CLI.
```

## Analytics notebooks

Executed analytics notebooks live under `docs/examples/analytics/` and are published to the
documentation site. They showcase deterministic playback, stochastic robustness, telemetry
diagnostics, and benchmarking workflows. Regenerate them locally with:

```bash
python scripts/run_analytics_notebooks.py --light
```

The `--light` flag mirrors CI: it sets `FHOPS_ANALYTICS_LIGHT=1`, trimming stochastic sample counts so
the suite finishes quickly. Drop the flag (or unset the environment variable) when you want the full
ensemble versions.

## Telemetry & Tuning

Heuristic sweeps (`fhops tune-random`, `fhops tune-grid`, `fhops tune-bayes`) log every run to
`telemetry/runs.jsonl` and mirror the data into a SQLite store. Aggregate the results with:

```bash
fhops telemetry report telemetry/runs.sqlite \
    --out-csv tmp/tuner_report.csv \
    --out-markdown tmp/tuner_report.md
```

CI executes lightweight sweeps on the **minitoy** and **med42** example scenarios for every run and
uploads the resulting `telemetry-report` artefact (Markdown + CSV) so you can track baseline
performance. The workflow also archives each run under `history/` and ships
`history_summary.{csv,md,html}` for quick trend analysis. See
`docs/howto/telemetry_tuning.rst` for a step-by-step guide and download instructions.
`history_delta.{csv,md}` capture latest-vs-previous deltas so regressions stand out instantly.
The latest per-scenario leaderboard lives in the Pages bundle at
`https://ubc-fresh.github.io/fhops/telemetry/latest_tuner_summary.md` and
`https://ubc-fresh.github.io/fhops/telemetry/latest_history_summary.md`, summarising the
strongest algorithm/objective per scenario for the current CI run without downloading artefacts.
Deeper comparisons (`tuner_comparison.*`, `tuner_leaderboard.*`) contrast grid/random/Bayesian
strategies with win rates, average deltas, and runtime stats.
Grab them straight from GitHub Pages via
`https://ubc-fresh.github.io/fhops/telemetry/latest_tuner_comparison.md` and
`latest_tuner_leaderboard.md` (CSV siblings share the same names).
Per-bundle splits (`tuner_comparison_baseline.*`, `tuner_comparison_synthetic.*`, …) and scenario
difficulty tables (`tuner_difficulty*.{md,csv}`) expose bundle-specific rankings, MIP gaps, and
second-best deltas for quick triage. When you include `--telemetry-log` in
`scripts/analyze_tuner_reports.py`, the convergence CSV/Markdown adds richer gap diagnostics:

- `baseline_objective`: starting objective recorded in telemetry.
- `gap_absolute = Z* – Zrun`: objective delta in native units (sign-agnostic).
- `gap_range = clamp((Z* – Zrun) / (Z* – Zbaseline), 0..1)`: fraction of distance between the
  baseline solution and the MIP optimum still remaining, robust to negative objectives.

Use ``scripts/run_tuning_benchmarks.py --plan baseline-smoke`` to reproduce the CI smoke sweep
over minitoy+med42 with aligned budgets; the ``synthetic-smoke`` and ``full-spectrum`` plans extend
the same matrix to synthetic tiers.

All tuning commands accept `--bundle` to expand scenario manifests. Built-in aliases include
`baseline` (minitoy + med42) and the synthetic tiers (`synthetic`, `synthetic-small`, etc.).
Combine aliases or point to your own `metadata.yaml` via `alias=/path/to/metadata.yaml` to run
sweeps across curated scenario sets while keeping telemetry labelled with the originating bundle.

When GitHub Pages is enabled, the CI workflow publishes the latest history bundle at
`telemetry/history_summary.html` on your Pages site (for example,
`https://ubc-fresh.github.io/fhops/telemetry/history_summary.html`), providing an
easily-shareable chart showing objective and KPI trends without downloading artefacts.
