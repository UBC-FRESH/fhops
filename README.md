# FHOPS — Forest Harvesting Operations Planning System

FHOPS is a Python package and CLI for building, solving, and evaluating
forest harvesting operations plans. It provides:
- A **data contract** (Pydantic models) for blocks, machines, landings, calendars.
- A **deterministic MIP** builder using **Pyomo**, with **HiGHS** as the default solver.
- A **metaheuristic engine** (Simulated Annealing v0.1) with pluggable operators.
- A CLI (`fhops`) to validate data, solve with MIP or heuristics, and evaluate results.

## Quick start (development install)

```bash
# inside a fresh virtual environment (Python 3.12+ recommended)
pip install -e .[dev]
# optional extras for spatial IO
pip install .[geo]

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

## Package layout

- `fhops.scenario`: Data models and the `Problem` container.
- `fhops.scenario.io`: Loaders and IO helpers (CSV/YAML, mobilisation distances).
- `fhops.optimization.mip`: Pyomo model builder + driver.
- `fhops.optimization.heuristics`: Metaheuristic solvers and operators.
- `fhops.evaluation`: Schedule playback and KPI reporting.
- `fhops.cli`: Typer-based CLI.

# What is FHOPS?

FHOPS (Forest Harvesting Operations Planning System) is a research-grade framework for **building, solving, and evaluating** forest harvesting operations plans. It gives you:

- a clean **data contract** for operational planning instances (blocks, machines, landings, calendars, production rates),
- an **optimization layer** (exact MIP + metaheuristics) to generate candidate schedules, and
- a **simulation/evaluation layer** to play back schedules deterministically or under uncertainty and report KPIs.

The goal is to give students and practitioners a **transparent, reproducible sandbox** where new constraints, objectives, and operators can be added incrementally, then stress-tested on repeatable scenarios.


## What problems does FHOPS solve?

Typical questions we can explore:

- Which blocks should each machine work on each day to **maximize delivered volume** (or minimize cost) while respecting **availability windows**, **landing capacity**, and **crew calendars**?
- How sensitive is the plan to **downtime**, **weather blackouts**, or **landing congestion**?
- When is an **exact MIP** viable, and when do we need a **heuristic** (and how close does it get)?


## Planning model (v0.1 scope)

- **Time**: discrete days over a planning horizon.
- **Entities**:
  - **Blocks**: `work_required`, `landing_id`, start/finish windows.
  - **Machines**: per-day availability (via calendar), optional crew tag, cost, daily hours.
  - **Landings**: per-day capacity on concurrent machine assignments.
- **Decision**: assign at most one block per machine per day; produce per-day **work** when assigned.
- **Constraints**: block windows, machine availability, landing daily capacity, block completion (cumulative work ≤ required).
- **Objective (default)**: **maximize total production** (bounded by work required). Hooks exist for penalties (moves/setup, lateness, congestion).

> **Rate semantics:** production rates are **per day when assigned** (v0.1). If you prefer “per hour,” change one line in the model/evaluator to multiply by `daily_hours`.


## Simulation & evaluation

The **simulation layer** is a deterministic schedule playback with optional stochastic extensions:

- **Deterministic playback**: compute realized production from a schedule + rates, enforce windows/availability/capacity, and accumulate KPIs.
- **KPIs (starter set)**: total production, completed blocks count; easy to extend with cost, makespan, utilization, penalty tallies.
- **Stochastic playback (roadmap)**: Monte-Carlo sampling of downtime/weather to estimate expected KPIs and plan robustness (stubs scaffolded for v0.1.x).

This separation lets you **optimize** with one set of assumptions and **evaluate** under another, without entangling solver internals.


## Architecture at a glance

```
fhops/
  core/     # Pydantic models: Block, Machine, Landing, Calendar, Rates, Scenario, Problem
  data/     # YAML + CSV loaders/validators; future Geo (GPKG) IO stubs
  model/    # Pyomo MIP builder (HiGHS by default); constraints & objectives organized modularly
  solve/    # highs_mip (exact) + heuristics/ (SA, Tabu/ILS scaffold), operators
  eval/     # schedule playback, KPIs; (robustness/MCS scaffolds)
  cli/      # Typer CLI: validate, build-mip, solve-mip, solve-heur, evaluate, benchmark
  examples/ # small/medium/large scenarios for testing & benchmarking
```

**Design principles**
- **Separation of concerns**: data ↔ model ↔ solvers ↔ evaluation.
- **Reproducible**: fixed seeds, example fixtures, CI tests, pinned env printed via CLI.
- **Extensible**: add constraints/operators without rewriting the world.


## Data contract (CSV + YAML)

A scenario is a YAML pointing to CSVs:

```yaml
name: My Scenario
schema_version: 1.0.0
num_days: 42
start_date: "2025-01-01"
data:
  blocks: data/blocks.csv          # id, landing_id, work_required, earliest_start, latest_finish
  machines: data/machines.csv      # id, crew, daily_hours, operating_cost
  landings: data/landings.csv      # id, daily_capacity
  calendar: data/calendar.csv      # machine_id, day, available (0/1)
  prod_rates: data/prod_rates.csv  # machine_id, block_id, rate  (per-day when assigned)
  mobilisation_distances: data/mobilisation_distances.csv
  crew_assignments: data/crew_assignments.csv
  geo_block_path: data/blocks.geojson
  geo_landing_path: data/landings.geojson
  geo_crs: EPSG:3005
locked_assignments:
  - machine_id: YARDER1
    block_id: B12
    day: 5
objective_weights:
  production: 1.0
  mobilisation: 1.0
```

Minimum required columns are shown above; extra columns are allowed and can be used by custom constraints/operators.


## Typical workflow

1) **Validate inputs**
```bash
fhops validate examples/minitoy/scenario.yaml
```

2) **Build and solve (exact)**
```bash
fhops solve-mip examples/minitoy/scenario.yaml   --out examples/minitoy/out/mip_solution.csv
```

3) **Solve (heuristic) for larger cases**
```bash
fhops solve-heur examples/large84/scenario.yaml   --out examples/large84/out/sa_solution.csv --iters 20000 --seed 1
```

4) **Evaluate KPIs for any schedule**
```bash
fhops evaluate examples/large84/scenario.yaml examples/large84/out/mip_solution.csv
```

5) **Benchmark**
```bash
fhops benchmark examples/med42/scenario.yaml --time_limit 60 --iters 8000
```


## Solvers & scaling

- **MIP** (Pyomo + HiGHS): great for small/medium instances; gives certificates and tight baselines.
- **Metaheuristics** (SA v0.1; Tabu/ILS scaffolded): scale to larger instances, flexible with new constraints, good for “what-if” exploration.

**Rule of thumb**
- **Small** (≤ 5 machines, ≤ 10 blocks, ≤ 21 days): try MIP first.
- **Medium** (≈ 8×20×42): MIP may work with time limits; heuristic recommended for fast iteration.
- **Large** (≈ 16×50×84 and up): heuristic first; use MIP on smaller sub-scenarios to calibrate.


## Extending FHOPS

### Add a new constraint (MIP)
- Implement it in `fhops/model/pyomo_builder.py` (or as a function under `model/constraints/`).
- Use the scenario fields you need (add to data contract if necessary).

## Project Docs & Planning Artefacts

- Roadmap: `FHOPS_ROADMAP.md` (mirrors detailed module notes in `notes/`).
- Coding agent workflow: `CODING_AGENT.md` with required command cadence.
- Change log: `CHANGE_LOG.md` tracks daily progress and executed commands.
- Documentation: Sphinx sources live under `docs/` and publish to Read the Docs.
- CI/CD: see `.github/workflows/ci.yml` for lint/type/test/doc automation.
- Add a tiny unit test + one example that tickles the constraint.

### Add a new operator/neighborhood (heuristics)
- Drop it under `fhops/solve/heuristics/operators.py` (or equivalent).
- Wire it into SA/ILS/Tabu.
- Mirror the logic in the evaluator to keep solver/eval semantics aligned.

### Add a KPI or penalty
- Update `fhops/eval/kpis.py` and (optionally) the MIP objective to keep apples-to-apples comparisons.


## Limitations (v0.1)

- No explicit **move/setup** time modeling (yet)—easy to add as a penalty or day-blocking constraint.
- No **trucking/haul** module (interfaces sketched for v0.1.x).
- **Spatial routing** is not built-in; precompute travel times and pass them in (Geo I/O stubs planned).
- The heuristic objective matches the deterministic evaluator; if you change objective terms, update both sides.


## Datasets shipped

- `examples/minitoy/` — tiny sanity instance.
- `examples/med42/` — 8 machines × 20 blocks × 42 days.
- `examples/large84/` — 16 machines × 50 blocks × 84 days.

Use these to verify install, compare solvers, and baseline new constraints.


## Why this framework?

- **Teaches the craft**: clean separation of data, model, solution, and evaluation makes it easy for a student to add one idea at a time and see its effect.
- **Reproducibility > mystique**: experiments are YAML-driven, solver settings explicit, outputs versioned, and tests guard the invariants.
- **Pragmatism**: exact where possible; smart heuristics where it matters.


## License

MIT
