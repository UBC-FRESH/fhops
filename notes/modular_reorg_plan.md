# FHOPS Modular Reorganisation Plan

Date: 2025-11-07
Status: Draft — capture proposed structure before code moves.

## Goals
- Mirror Nemora’s domain-first layout so FHOPS scales cleanly as we add mobilisation, shift-level scheduling, and harvest-system features.
- Isolate scenario definition/generation from optimisation and evaluation code.
- Provide clear module boundaries for upcoming thesis-aligned workstreams (synthetic datasets, system sequencing, mobilisation costs).

## Proposed Directory Layout

```
src/fhops/
    core/             # shared constants, enums, logging helpers
    scenario/
        contract/     # Pydantic models and validators
        io/           # YAML/CSV readers/writers, schema checks
        synthetic/    # dataset generators, parameter samplers
    scheduling/
        timeline/     # day/shift calendars, blackout logic, reporting bins
        mobilisation/ # distance calculators, setup/move costs
        systems/      # harvest system registry, machine/worker capability maps
    optimization/
        mip/          # Pyomo builders segmented by constraint module
        heuristics/   # SA/Tabu/ILS operators and runners
        constraints/  # reusable constraints (mobilisation, sequencing, etc.)
    evaluation/
        playback/     # deterministic + stochastic schedule replay
        metrics/      # KPI computations and weekly aggregations
        reporting/    # output writers, visualisation hooks
    cli/              # Typer commands delegating to the modular APIs
```

## Migration Phases
1. **Scaffolding**
   - Create package skeletons (`__init__.py`, docstrings) and update import paths in docs/tests as placeholders. ✅ scaffolded (`src/fhops/{scenario,scheduling,optimization,evaluation}/...`).
   - Seed module-specific notes (`notes/mobilisation_plan.md`, `notes/synthetic_dataset_plan.md`, `notes/system_sequencing_plan.md`).

2. **Scenario & Scheduling Split**
   - Move existing Pydantic models and loaders into `scenario/contract` and `scenario/io`. ✅ models/loaders migrated with shims.
- [x] Create `scheduling/timeline` for shift/day calendars and blackout metadata (models + loader support).

3. **Optimisation Restructure**
   - Partition Pyomo builder into submodules (`optimization/mip/constraints/*.py`). ✅ baseline builder/HiGHS driver migrated.
   - Relocate heuristics into `optimization/heuristics` with operator registry. ✅ SA ported.

4. **Mobilisation & Systems**
   - Implement mobilisation cost calculators and system sequencing logic in new modules.
   - Update MIP/heuristics to consume the modular pieces.

5. **Evaluation & Reporting**
   - Move KPI code into `evaluation/metrics`, playback into `evaluation/playback`, docs accordingly. ✅ KPI helper moved; playback still pending.

6. **Docs & CI Refresh**
   - Update Sphinx autosummary entries, CLI docs, and tests to the new imports.
   - Ensure CI/ruff/mypy paths reflect the reorganised packages.

## Dependencies & Considerations
- Coordinate with `notes/data_contract_enhancements.md` and `notes/mip_model_plan.md` to keep tasks aligned with the new structure.
- Document each migration step in CHANGE_LOG and roadmap to avoid confusion during refactors.
- Keep tests green between phases—introduce adapters/shim imports if necessary to avoid breaking downstream code.

## Phase 2 Shift-Based Scheduling Initiative
- **Objective:** replace day-indexed scheduling with shift-indexed scheduling across scenario inputs, optimisation models, heuristics, KPIs, and CLI tooling.
- **Key Deliverables**
  - Shift-aware data contract (CSV/YAML schema for shifts, updated `TimelineConfig`).
  - Updated `Problem` representation exposing `(day, shift)` timeline, plus backwards-compatible loaders.
  - MIP/heuristic refactor with shift-indexed decision variables and operator support.
  - KPI/benchmark updates outputting both shift-level and aggregated metrics.
  - Documentation & migration guidance for existing scenarios.
- **Work Breakdown**
  1. **Contract & IO:** add shift tables/fields, loader validation, default single-shift migration path.
  2. **Core Model:** adjust `Problem` and helper APIs to reason in shifts, propagate mobilisation/sequencing/timeline constraints.
  3. **Optimisation:** re-index Pyomo variables/constraints, revisit mobilisation and sequencing logic for intra-day moves, ensure heuristics operate on shifts (including new operators).
  4. **Evaluation:** modify KPIs and playback to accept shift-level assignments; expose shift filters in CLI/benchmarks.
  5. **Regression & Docs:** update sample scenarios (minitoy/med42/large84) with synthetic shifts, refresh fixtures, and document migration steps in data contract & CLI guides.
