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
| Small  | 4–6    | 2–3      | 1        | 6–8  | 1          | 1–2              | 6–10      | 8–14                | Mirrors minitoy scale; no downtime. |
| Medium | 8–12   | 4–6      | 2–3      | 10–14| 1          | 2–3              | 8–14      | 8–16                | Introduce short blackouts and role-mixed crews. |
| Large  | 14–24  | 6–10     | 3–5      | 16–24| 2          | 2–4              | 10–18     | 10–18               | Two-shift calendars, extended downtime, optional system presets. |

All tiers share a consistent column layout (see `examples/synthetic/metadata.yaml`) so benchmark scripts can treat them uniformly. Additional knobs:

- **Terrain/Prescription tags** — recorded on each block (``terrain``/``prescription`` columns) with tier defaults; future contract updates can promote these to formal scenario tags.
- **Crew capability pools** — leverage `role_pool` and future worker capability matrices.
- **Blackout windows** — probabilistic sampling tuned per tier (`0.0`, `0.1`, `0.2` respectively).
- **Crew assignment CSVs** — each scenario now writes `crew_assignments.csv` so solvers/validators can recover crew → machine mappings without custom wiring.
- **Metadata registry** — per-tier `metadata.yaml` files summarise terrain/prescription counts, crew capabilities, blackout windows, and seeds; the aggregate `examples/synthetic/metadata.yaml` collates them for automation.

## Benchmarking Alignment

We will integrate the reference bundles into the Phase 2 benchmarking harness with the following guardrails:

1. **Scenario Registry** — expose `examples/synthetic/{small,medium,large}` through a lightweight registry module so `fhops bench suite --scenario synthetic:small` is possible.
2. **Metric Coverage** — ensure KPI smoke tests hit all tiers (deterministic + stochastic) and capture regression snapshots under `tests/test_benchmarks_synthetic.py`.
3. **Runtime Budgets** — align SA/ILS defaults to keep executions under 60 s for CI, with expanded presets documented for deeper experiments.
4. **Result Storage** — reuse the existing benchmarking output structure (`tmp/benchmarks/...`) and document the synthetic-specific expectations in `docs/howto/benchmarks.rst`.

## Planned Tasks
- [x] Define configuration schema for synthetic dataset generator (`scenario/synthetic/generator.py`).
- [x] Support basic timeline blackouts and harvest system role assignment in synthetic scenarios.
- [x] Implement randomised and template-driven generators producing YAML/CSV bundles.
- [x] Produce reference datasets (small/medium/large) with metadata for benchmarking (`examples/synthetic/`).
- [x] Hook dataset generation into tests/CI where feasible. *(See `tests/test_synthetic_dataset.py`.)*

## Tests & Validation
- [x] Unit tests ensuring generated datasets satisfy scenario contract validators. *(See `tests/test_synthetic.py`.)*
- [x] Statistical checks on sampled parameters (distributions, workload constraints).

## Documentation
- [x] Sphinx guide on generating and using synthetic datasets.
- [x] Example CLI or script usage for students.

## Dependencies
- Align with `notes/data_contract_enhancements.md` (worker skills, system definitions).
- Coordinate with evaluation/benchmarking plans to keep outputs consistent.
