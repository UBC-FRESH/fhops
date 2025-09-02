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

# Try the tiny example:
fhops validate examples/minitoy/scenario.yaml
fhops solve-mip examples/minitoy/scenario.yaml --out examples/minitoy/out/mip_solution.csv
fhops solve-heur examples/minitoy/scenario.yaml --out examples/minitoy/out/sa_solution.csv
fhops evaluate examples/minitoy/scenario.yaml examples/minitoy/out/mip_solution.csv
```

## Package layout

- `fhops.core`: Data models and the `Problem` container.
- `fhops.data`: Loaders and IO helpers.
- `fhops.model`: Pyomo model builder.
- `fhops.solve`: MIP and heuristic solvers.
- `fhops.eval`: Schedule playback and KPI reporting.
- `fhops.cli`: Typer-based CLI.

## License
MIT
