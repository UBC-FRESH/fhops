# Tactical–Operational Compatibility Baseline

Date: 2026-09-24  
Issues: #36, #37

## Purpose

Phase 6 must add TOPM-like tactical–operational planning without destabilizing the operational
FHOPS contract or CLI. This note records the baseline that child issues #38–#44 must preserve.

## Stable operational contract

The current operational contract is `fhops.scenario.contract.models.Scenario`, schema `1.0.0`, with
these invariant behaviors:

- `Scenario.num_days` defines the operational day horizon.
- `Problem.from_scenario()` expands days and shift slots, synthesizing a single `S1` shift for
  legacy day-level scenarios.
- Blocks reference known landings and optional harvest systems.
- Calendars and shift calendars cannot exceed `num_days`.
- Production rates reference known machine/block pairs.
- Mobilisation, locked assignments, objective weights, GeoJSON metadata, crew assignments, and road
  construction records are validated before solving.
- Existing YAML/CSV scenario bundles remain loadable without tactical–operational fields.

## CLI workflows to preserve

The following public workflows must continue to work unchanged unless a maintainer-approved
migration says otherwise:

```bash
fhops validate examples/tiny7/scenario.yaml
fhops solve-mip examples/tiny7/scenario.yaml --out /tmp/tiny7_mip.csv
fhops solve-heur examples/tiny7/scenario.yaml --out /tmp/tiny7_sa.csv --iters 25 --seed 7
fhops evaluate examples/tiny7/scenario.yaml --assignments /tmp/tiny7_sa.csv
fhops plan rolling examples/tiny7/scenario.yaml --master-days 7 --sub-days 7 --lock-days 7 --solver sa
```

## Python APIs to preserve

- `fhops.scenario.io.load_scenario(...)`
- `fhops.scenario.contract.Problem.from_scenario(...)`
- `fhops.model.milp.data.build_operational_bundle(...)`
- `fhops.model.milp.operational.build_operational_model(...)`
- `fhops.model.milp.driver.solve_operational_milp(...)`
- `fhops.optimization.heuristics` solver entry points
- `fhops.planning.solve_rolling_plan(...)`
- `fhops.evaluation.compute_kpis(...)` and playback adapters/exporters

## Reference scenarios and fixtures

Preserve the operational ladder and regression fixtures:

- `examples/tiny7`
- `examples/small21`
- `examples/med42`
- `examples/large84`
- `examples/synthetic`
- `tests/fixtures/regression`
- `tests/fixtures/milp`
- `tests/fixtures/playback`
- `tests/fixtures/kpi`
- `tests/fixtures/benchmarks`

## Compatibility tests to run for every Phase 6 child issue

At minimum, each child issue must run or explicitly justify skipping:

```bash
ruff format src tests
ruff check src tests
mypy src
pytest
pre-commit run --all-files
sphinx-build -b html docs _build/html -W
```

When the local virtual environment is unavailable, the child PR must state that limitation and run
whatever focused checks are available (for example `ruff`, `git diff --check`, schema/spec tests, or
targeted CI jobs).

## Guardrails for Phase 6

1. Do not change `Scenario` schema `1.0.0` semantics.
2. Do not rename or remove public operational APIs in Phase 6.
3. Do not add tactical–operational fields to the operational `Scenario` contract; use explicit
   contract dispatch instead.
4. Do not stretch `Problem.shifts` or the operational MILP to a multi-year horizon.
5. Do not couple optional roads/silviculture/fleet modules to the core product-flow model without
   module toggles.
6. Keep `main` free of Phase 6 implementation until child PRs merge through the Phase 6 integration
   branch or a maintainer-approved direct PR.
