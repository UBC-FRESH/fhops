# FHOPS Examples

This directory contains FHOPS example scenarios and the onboarding notebook series.

## Bundled Scenarios

| Directory | Horizon | Blocks | Machines | Description |
| --- | --- | --- | --- | --- |
| `tiny7/` | 7 days | 2 | 9 | Smallest scenario; ideal for quick iteration. |
| `small21/` | 21 days | 6 | 9 | Small scenario with 3 large blocks. |
| `med42/` | 42 days | 12 | 9 | Medium scenario for stochastic analysis. |
| `synthetic/small/` | 112 days | variable | variable | Synthetic ground-based scenario. |
| `synthetic/medium/` | 112 days | variable | variable | Synthetic medium scenario. |
| `synthetic/large/` | 112 days | variable | variable | Synthetic large scenario. |

All scenarios use Lahrsen-aligned stand attributes and FHOPS productivity
regressions (Lahrsen harvesters, ADV6N7 grapple skidders, Berry 2019
processors, TN-261 loaders).

## Setup

```bash
# Install fhops in editable/development mode (source checkout)
pip install -e .

# Optional: install dev dependencies
pip install -e ".[dev]"
```

## Launch Jupyter

```bash
cd examples
jupyter notebook
```

Open the notebooks in order: `00_fhops_orientation.ipynb` through
`04_fhops_stochastic_what_if.ipynb`.

## Run the onboarding notebooks from the command line

```bash
python scripts/run_example_notebooks.py

# Run one notebook using a numeric shorthand alias.
python scripts/run_example_notebooks.py --notebook 01

# Repeat --notebook to select several notebooks.
python scripts/run_example_notebooks.py --notebook 00 --notebook 02

# Full notebook names are accepted too.
python scripts/run_example_notebooks.py --notebook 01_fhops_operations_simulation
```

Options:
- `--light` — skip heavy/heuristic steps.
- `--keep-going` — continue after a failure.
- `--timeout N` — per-notebook timeout in seconds (default: 600).
- `--notebook NAME` — run only specific notebooks (repeatable); use `00`, `01`,
   `02`, `03`, or `04` as shorthand aliases (with an optional `.ipynb` suffix), or
   pass a full notebook name such as `01_fhops_operations_simulation`.

Notebook execution writes to an untracked temporary output directory by
default and **never** overwrites source notebooks.

## Notebook sequence

1. **`00_fhops_orientation.ipynb`** — locate the repo, discover and inspect
   scenarios via `fhops.scenario.load_scenario` and `Problem.from_scenario`,
   call the CLI `validate` command, and exercise the notebook-local AAM helpers
   (`diagnose_config`, `rtfm`, `explain_workflow`, `build_node`).

2. **`01_fhops_operations_simulation.ipynb`** — inspect Tiny7 blocks, machines,
   harvest-system workflow, registry contexts, and source-based productivity
   helpers, then replay valid and intentionally invalid operational assignments.
   This is the operations-simulation core; playback evaluates assignments and
   does not optimise them.

3. **`02_fhops_solve_compare.ipynb`** — solve `tiny7` and `small21` with the
   simulated annealing heuristic via both the Python API
   (`fhops.optimization.heuristics.solve_sa`) and the CLI
   (`fhops solve-heur`), then compare objectives, KPIs, and schedule summaries.

4. **`03_fhops_playback_kpis.ipynb`** — run deterministic playback
   (`fhops.evaluation.playback.run_playback`), produce shift/day summary
   DataFrames, and compute KPIs (`fhops.evaluation.compute_kpis`).

5. **`04_fhops_stochastic_what_if.ipynb`** — solve `med42` with SA, then run
   stochastic playback with sampling
   (`fhops.evaluation.run_stochastic_playback` + `SamplingConfig`) to assess
   schedule robustness under downtime, weather, and landing-shock uncertainty.

## Dataset reuse

All five onboarding notebooks use the **bundled** scenarios under `examples/`.
No external datasets or licensed solvers are required. Heuristic budgets are
kept modest (50–200 SA iterations, seeds 7 or 42) for reproducibility.

Solver/CLI outputs (CSV assignments) are created in `tempfile.TemporaryDirectory`
during execution and cleaned up automatically.

## Helper module: `notebook_support.py`

`examples/notebook_support.py` provides notebook-local helper functions.
These are **not** part of the public `fhops` package API — treat them as
example code. The module covers:

- Repository and scenario dataset discovery.
- Structured `fhops` CLI invocation.
- Compact schedule validation.
- Display-friendly scenario/schedule summaries.
- AAM-style helper callables (`explain_workflow`, `diagnose_config`,
  `build_node`, `rtfm`, `inspect_scenario`, `preview_schedule`).

All AAM callables return structured dictionaries with explicit `ok`,
`operation`/`name`, `errors`, `provenance`, and an `executed` vs
`review_only` distinction.

## Existing analytics notebooks

Historical analytics notebooks are maintained under
`docs/examples/analytics/`. Those notebooks are separate from this onboarding
series and pre-date it.
