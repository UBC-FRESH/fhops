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

## Phase 2 Shift-Based Scheduling Initiative ✅
- Shift-aware data contract (`TimelineConfig`, shift calendars, mobilisation schemas) ships in `fhops.scenario.contract`; loaders ingest timelines/blackouts/crew metadata with regression fixtures covering minimal/typical scenarios.
- `Problem.shifts` now drives the Pyomo builder and heuristics, enforcing blackout windows and mobilisation constraints across `(day, shift)` tuples.
- Playback, KPI aggregators, and exporters emit shift/day summaries; CLI plus telemetry workflows surface the new metrics (CSV/Parquet/Markdown).
- Example scenarios and docs were refreshed to include shift calendars, and tests assert loader + solver behaviour.
- Remaining related work is tracked under the geospatial intake and mobilisation/system-sequencing plans rather than this initiative.
