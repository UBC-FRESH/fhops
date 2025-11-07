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

## Planned Tasks
- [x] Define configuration schema for synthetic dataset generator (`scenario/synthetic/generator.py`).
- [ ] Implement randomised and template-driven generators producing YAML/CSV bundles.
- [ ] Produce reference datasets (small/medium/large) with metadata for benchmarking.
- [ ] Hook dataset generation into tests/CI where feasible.

## Tests & Validation
- [x] Unit tests ensuring generated datasets satisfy scenario contract validators. *(See `tests/test_synthetic.py`.)*
- [ ] Statistical checks on sampled parameters (distributions, workload constraints).

## Documentation
- [ ] Sphinx guide on generating and using synthetic datasets.
- [ ] Example CLI or script usage for students.

## Dependencies
- Align with `notes/data_contract_enhancements.md` (worker skills, system definitions).
- Coordinate with evaluation/benchmarking plans to keep outputs consistent.
