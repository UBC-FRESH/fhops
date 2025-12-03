# Synthetic Dataset Plan

Date: 2025-11-07
Status: Draft — groundwork for thesis-aligned datasets.

## Objectives
- Generate synthetic scenarios spanning size, system types, crews, and worker capability variations.
- Provide parameterised templates so students can reproduce and extend datasets.
- Integrate dataset generation with benchmarking harnesses and documentation.

## Dimensions to Sample
- Instance scale: blocks, days/shifts, landings, machines, crews, workers.
- Harvest systems: registry of system archetypes with machine/job mappings and environment tags.
- Workforce: training capabilities, max workloads (daily, weekly), multi-skill workers.
- Environment: terrain, species mix, prescription type (thinning, clearcut, VR).

## Dataset Taxonomy & Parameter Ranges

| Tier   | Blocks | Machines | Landings | Days | Shifts/Day | Landing Capacity | Work (m³) | Prod. Rate (m³/hr) | Notes |
|--------|--------|----------|----------|------|------------|------------------|-----------|---------------------|-------|
| Small  | 4–6    | 2–3      | 1        | 6–8  | 1          | 1–2              | 6–10      | 8–14                | Mirrors tiny7 scale; no downtime. |
| Medium | 8–12   | 4–6      | 2–3      | 10–14| 1          | 2–3              | 8–14      | 8–16                | Introduce short blackouts and role-mixed crews. |
| Large  | 14–24  | 6–10     | 3–5      | 16–24| 2          | 2–4              | 10–18     | 10–18               | Two-shift calendars, extended downtime, optional system presets. |

All tiers share a consistent column layout (see `examples/synthetic/metadata.yaml`) so benchmark scripts can treat them uniformly. Additional knobs:

- **Terrain/Prescription tags** — recorded on each block (``terrain``/``prescription`` columns) with tier defaults; future contract updates can promote these to formal scenario tags.
- **Crew capability pools** — leverage `role_pool` and future worker capability matrices.
- **Blackout windows** — probabilistic sampling tuned per tier (`0.0`, `0.1`, `0.2` respectively).
- **Crew assignment CSVs** — each scenario now writes `crew_assignments.csv` so solvers/validators can recover crew → machine mappings without custom wiring.
- **Metadata registry** — per-tier `metadata.yaml` files summarise terrain/prescription counts, crew capabilities, blackout windows, and seeds; the aggregate `examples/synthetic/metadata.yaml` collates them for automation.
- **Sampling utilities** — weighted terrain/prescription profiles, blackout bias windows (`BlackoutBias`), and harvest system mixes are now configurable in `generator.py`, with the selected profiles recorded in bundle metadata.

## CLI Generation Command

We will surface the generator via ``fhops synth`` so bundles can be created without writing ad-hoc scripts.

**Command shape**

```
fhops synth generate [OUTPUT_DIR] \
  --tier {small,medium,large,custom} \
  --config config.yaml \
  --seed 123 \
  --overwrite \
  --preview
```

- ``OUTPUT_DIR`` defaults to ``examples/synthetic/<tier>`` when omitted.
- ``--tier`` loads the canonical preset (matching ``TIER_DEFAULTS`` in the generator); ``custom`` requires
  either ``--config`` or individual overrides.
- ``--config`` points to a YAML/TOML file serialising ``SyntheticDatasetConfig`` (fields other than
  ``name`` default to the preset, so users can override a subset).
- ``--seed`` sets the RNG seed; when omitted, default to the preset seed (`metadata.yaml` should record it).
- ``--overwrite`` removes an existing directory; otherwise command aborts if outputs already exist.
- ``--preview`` prints the sampled counts/metadata instead of writing files (useful for notebooks).

**Configuration serialisation**

Schema mirrors ``SyntheticDatasetConfig`` with camel-case keys for CLI ergonomics:

```yaml
name: synthetic-custom
num_blocks: [10, 14]
num_days: 14
num_machines: [5, 6]
num_landings: 3
shifts_per_day: 1
shift_hours: [9.0, 10.5]
landing_capacity: [2, 3]
work_required: [8.0, 16.0]
production_rate: [8.0, 16.0]
availability_probability: 0.85
blackout_probability: 0.15
blackout_duration: [1, 2]
terrain_pool: ["rolling", "steep"]
prescription_pool: ["thinning", "clearcut"]
crew_pool: ["crew-alpha", "crew-beta"]
capability_pool: ["harvester", "forwarder", "processor"]
crew_capability_span: [1, 2]
```

When both ``--tier`` and ``--config`` are provided, we merge defaults (tier → seed/pools/blackouts) with
explicit overrides. CLI should also expose lightweight flags for the most common tweaks (`--blocks`,
`--machines`, `--landings`, `--days`, `--shifts-per-day`) so instructors can craft variations quickly.

## Benchmarking Alignment

We will integrate the reference bundles into the Phase 2 benchmarking harness with the following guardrails:

1. **Scenario Registry** — expose `examples/synthetic/{small,medium,large}` through a lightweight registry module so `fhops bench suite --scenario synthetic:small` is possible.
2. **Metric Coverage** — ensure KPI smoke tests hit all tiers (deterministic + stochastic) and capture regression snapshots under `tests/test_benchmarks_synthetic.py`.
3. **Runtime Budgets** — align SA/ILS defaults to keep executions under 60 s for CI, with expanded presets documented for deeper experiments.
4. **Result Storage** — reuse the existing benchmarking output structure (`tmp/benchmarks/...`) and document the synthetic-specific expectations in `docs/howto/benchmarks.rst`.

## Scaling Experiments (2025-11-11)

`run_benchmark_suite` smoke pass (`sa_iters=250`, `time_limit=15s`, SA only) across medium/large synthetic tiers:

| Scenario         | Objective | Runtime (s) | Total Production | Makespan (days) |
|------------------|-----------|-------------|------------------|-----------------|
| synthetic-medium | 92.235    | 0.05        | 92.235           | 12              |
| synthetic-large  | 176.808   | 0.10        | 176.808          | 17              |

Both tiers finish in under 0.1 seconds with the smoke settings, leaving ample headroom for CI checks and deeper stochastic experiments.

### Stochastic playback snapshot

Using the tier sampling presets (`sampling_config_for`) and replaying the SA assignments over the same scenarios:

| Scenario         | Samples | Mean Production | Std Production | Mean Weather Severity | Mean Utilisation |
|------------------|---------|-----------------|----------------|-----------------------|------------------|
| synthetic-medium | 12      | 25.55           | 4.16           | 0.27                  | 1.00             |
| synthetic-large  | 18      | 18.25           | 4.88           | 0.24                  | 1.00             |

Downtime shocks did not fire in the smoke run (probabilities are low for the short horizons), but the wiring ensures sample counts and weather effects are exercised in CI (`tests/test_synthetic_validation.py`).

## Planned Tasks
- [x] Define configuration schema for synthetic dataset generator (`scenario/synthetic/generator.py`).
- [x] Support basic timeline blackouts and harvest system role assignment in synthetic scenarios.
- [x] Implement randomised and template-driven generators producing YAML/CSV bundles.
- [x] Produce reference datasets (small/medium/large) with metadata for benchmarking (`examples/synthetic/`).
- [x] Hook dataset generation into tests/CI where feasible. *(See `tests/test_synthetic_dataset.py`.)*

## Tests & Validation
- [x] Unit tests ensuring generated datasets satisfy scenario contract validators. *(See `tests/test_synthetic.py`.)*
- [x] Statistical checks on sampled parameters (distributions, workload constraints).
- [x] Benchmark smoke validation verifying KPI bounds for reference bundles. *(See `tests/test_benchmark_harness.py::test_synthetic_small_benchmark_kpi_bounds`.)*
- [x] Property-based KPI sanity checks covering synthetic smoke runs. *(See `tests/test_benchmark_harness.py::test_synthetic_kpi_properties`.)*
- [x] Stochastic playback validation across small/medium tiers (`tests/test_synthetic_validation.py`).

## Documentation
- [x] Sphinx guide on generating and using synthetic datasets.
- [x] Example CLI or script usage for students.

## Dependencies
- Align with `notes/data_contract_enhancements.md` (worker skills, system definitions).
- Coordinate with evaluation/benchmarking plans to keep outputs consistent.
