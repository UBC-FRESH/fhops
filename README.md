# FHOPS — Forest Harvesting Operations Planning System

FHOPS is a Python package and CLI for building, solving, and evaluating
forest harvesting operations plans. It provides:
- A **data contract** (Pydantic models) for blocks, machines, landings, calendars.
- A **deterministic MIP** builder using **Pyomo**, with **HiGHS** as the default solver (optional **Gurobi** support when installed/licensed).
- A **metaheuristic engine** (Simulated Annealing v0.1) with pluggable operators.
- A CLI (`fhops`) to validate data, solve with MIP or heuristics, and evaluate results.

## Installation

```bash
pip install fhops  # once the release candidate lands on PyPI
```

For local development or when cutting a release candidate, use Hatch to mirror the CI suite:

```bash
pip install hatch
hatch run dev:suite
```

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
fhops validate examples/tiny7/scenario.yaml
fhops solve-mip examples/tiny7/scenario.yaml --out examples/tiny7/out/mip_solution.csv
fhops solve-heur examples/tiny7/scenario.yaml --out examples/tiny7/out/sa_solution.csv
fhops evaluate examples/tiny7/scenario.yaml examples/tiny7/out/mip_solution.csv
```

```bash
fhops solve-mip tests/fixtures/regression/regression.yaml --out /tmp/regression_mip.csv
fhops solve-heur tests/fixtures/regression/regression.yaml --out /tmp/regression_sa.csv
fhops evaluate tests/fixtures/regression/regression.yaml /tmp/regression_sa.csv
```

Expected evaluation output includes `sequencing_violation_count=0`. Mobilisation costs are
exercised in `tests/test_regression_integration.py`, which injects machine parameters before
running the CLI.
## Analytics notebooks & dashboards

Executed analytics notebooks live under `docs/examples/analytics/` and are published to the
documentation site. They showcase deterministic playback, stochastic robustness, telemetry
diagnostics, and benchmarking workflows. Regenerate them locally with:

```bash
python scripts/run_analytics_notebooks.py --light
```

The `--light` flag mirrors CI: it sets `FHOPS_ANALYTICS_LIGHT=1`, trimming stochastic sample counts so
the suite finishes quickly. Drop the flag (or unset the environment variable) when you want the full
ensemble versions.

Live dashboards (auto-published after every `main` build and the weekly full notebook run) live at
`https://ubc-fresh.github.io/fhops/reference/dashboards.html`. Highlights:

- Telemetry history trends and per-scenario leaderboards.
- Latest tuner reports, comparison tables, and win-rate leaderboards.
- Difficulty indices per bundle/tier and weekly notebook metadata archives.

Each dashboard entry includes regeneration commands so you can reproduce the artefacts locally.

### Tuned heuristic presets

Release candidate tuning runs are recorded in `notes/release_tuning_results.md`; the best operator
weights and configurations per scenario/algorithm are serialized in `notes/release_tuned_presets.json`.
Use these records when reproducing benchmarks or seeding custom presets, e.g.

```bash
python -c "import json; cfg=json.load(open('notes/release_tuned_presets.json')); print(cfg[0])"
# feed operator weights into fhops tune-random --operator-weight swap=... --operator-weight move=...
```

## Quick demos

Show off the tuning harness or heuristics in one command:

```bash
python scripts/run_tuning_benchmarks.py \
  --bundle synthetic-small \
  --out-dir tmp/demo-synth \
  --random-runs 1 --random-iters 400 \
  --grid-iters 400 --grid-preset explore \
  --bayes-trials 2 --bayes-iters 400 \
  --max-workers 8 \
&& column -t -s'|' tmp/demo-synth/tuner_report.md | sed 's/^/  /'
```

or run eight random restarts per heuristic on the baseline bundle:

```bash
python scripts/run_tuning_benchmarks.py \
  --bundle baseline \
  --out-dir tmp/demo-restarts \
  --tuner random --tuner ils --tuner tabu \
  --random-runs 8 --random-iters 400 \
  --ils-runs 8 --ils-iters 400 \
  --tabu-runs 8 --tabu-iters 2000 \
  --max-workers 8 \
&& column -t -s'|' tmp/demo-restarts/tuner_summary.md | sed 's/^/  /'
```

## Watching heuristics (live dashboard)

Most solver commands accept a `--watch/--no-watch` flag that renders a Rich dashboard while the run
is in progress:

```bash
fhops solve-heur examples/med42/scenario.yaml \
  --iters 200000 \
  --cooling-rate 0.99999 \
  --restart-interval 500 \
  --watch \
  --watch-refresh 0.5
```

The table shows shared metrics (scenario, solver, iteration, best/current/rolling objective,
runtime, restarts/workers) while the line below it displays solver-specific details (e.g., SA
temperature/acceptance, ILS perturbations, Tabu tenure). The dashboard refreshes only when FHOPS
detects an interactive terminal; in CI/non-TTY contexts it emits a single warning
(`Watch mode disabled: not running in an interactive terminal.`) and continues with the normal CLI
output.

The flag is available on:

- `fhops solve-heur`, `fhops solve-ils`, `fhops solve-tabu`
- `fhops tune-random`, `fhops tune-grid`, `fhops tune-bayes`
- `fhops bench suite --watch`

Adjust `--watch-refresh <seconds>` (default 0.5 s) to trade off responsiveness vs. terminal churn.
When using `--parallel-workers` remember that scoring still uses Python threads today, so the table’s
`workers` column reflects the requested worker count even though the GIL may limit true parallelism;
for real multi-core use prefer `--parallel-multistart` or process-level orchestration.

### FAQ – Watch Mode

- **“Watch mode disabled: not running in an interactive terminal.”**
  The dashboard only renders when stdout is a TTY. Wrap the command with `script` (or run it inside a
  terminal multiplexer) when you need both the live table and a log:

  ```bash
  script -q -c "fhops solve-heur ... --watch" /tmp/fhops_watch.log
  ```

  The TTY sees the dashboard, while the log captures the standard CLI output after the run.

- **How can I record a screenshot/GIF?**
  Run a short command (e.g., `fhops solve-heur examples/tiny7/scenario.yaml --watch --iters 500`)
  and use your preferred terminal recorder (`asciinema`, `ttystudio`, etc.). The sparkline now renders
  below the main table so column widths stay stable while recording.
