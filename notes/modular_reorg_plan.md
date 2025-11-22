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

## Phase 2 Shift-Based Scheduling Refactor Plan

### Goals
- Treat **shift** as a first-class time index (in addition to day) from scenario ingest through solvers, playback, KPIs, and CLI outputs.
- Preserve backward compatibility with day-only scenarios while encouraging authors to define named shifts per landing/system.
- Provide regression coverage and documentation so future contributor work does not regress shift awareness.

### Workstreams
1. **Data Contract & Fixtures**
   - Extend `TimelineConfig`/`ShiftDefinition` with explicit `shift_id`, `start_offset_hours`, and `duration_hours`.
   - Add `shifts` metadata to `Scenario` (e.g., `scenario.shift_calendar`) plus validators guaranteeing shift coverage of each day, optional default shift templates, and horizon alignment.
   - Update YAML/CSV fixtures (minitoy, med42, large84, regression set) to declare shifts; provide migration guidance for day-only scenarios.
2. **Loader & Core Types**
   - Teach `fhops.scenario.io.loaders` to emit `(day, shift_id)` availability matrices, synthesising a default single-shift calendar when absent.
   - Introduce helper utilities to iterate `Problem.iter_shifts()` and to convert between day-major and shift-major tensors (will be consumed by solvers/playback).
3. **Optimisation & Heuristics**
   - Rebuild Pyomo variables/constraints (assignment, mobilisation transitions, landing capacity, locking, sequencing) on `(day, shift)` indices. Provide compatibility adapters that aggregate to day totals when exporting KPIs or legacy outputs.
   - Update SA (and upcoming Tabu/ILS) neighbourhoods to operate on shift slots, including shift-aware locking, mobilisation penalties, and sequencing guards.
   - Capture performance notes in `notes/mip_model_plan.md` once shift-indexing lands (variable explosion mitigation, tighten bounds via shift availability).
4. **Playback, KPIs, Telemetry**
   - Implement converters from solver outputs to shift-indexed schedule frames, feeding deterministic playback and KPI calculators.
   - Ensure KPI exports clearly differentiate day vs shift totals, and extend telemetry records with shift counts to support tuning analysis.
5. **CLI, Docs, and Examples**
   - Add CLI flags/examples showing shift calendars (e.g., `fhops solve-mip --shifts day=1:shift=A/B`), update quickstart + data-contract how-to with step-by-step instructions.
   - Provide troubleshooting guidance for missing/overlapping shifts and document migration steps for legacy datasets.
6. **Testing & Validation**
   - Expand regression fixtures covering multi-shift calendars (e.g., day shift + night shift) and ensure both MIP/SA respect blackout windows per shift.
   - Property-based tests verifying that aggregated shift totals equal day totals; CLI smoke tests for shift-aware playback exports.

### Dependencies
- Coordinate tightly with `notes/mip_model_plan.md` (solver work), `notes/simulation_eval_plan.md` (playback/KPI alignment), and `notes/cli_docs_plan.md` (documentation + UX).
- Continue logging each milestone in `CHANGE_LOG.md` and referencing the relevant roadmap bullet when a workstream is finished.
