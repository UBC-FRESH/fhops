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

## Validate & Evaluate

```bash
fhops validate examples/minitoy/scenario.yaml
fhops solve-mip examples/minitoy/scenario.yaml --out examples/minitoy/out/mip_solution.csv
fhops solve-heur examples/minitoy/scenario.yaml --out examples/minitoy/out/sa_solution.csv
fhops evaluate examples/minitoy/scenario.yaml examples/minitoy/out/mip_solution.csv
```

```bash
fhops solve-mip tests/fixtures/regression/regression.yaml --out /tmp/regression_mip.csv
fhops solve-heur tests/fixtures/regression/regression.yaml --out /tmp/regression_sa.csv
fhops evaluate tests/fixtures/regression/regression.yaml /tmp/regression_sa.csv
```

Expected evaluation output includes `sequencing_violation_count=0`. Mobilisation costs are
exercised in `tests/test_regression_integration.py`, which injects machine parameters before
running the CLI.
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

