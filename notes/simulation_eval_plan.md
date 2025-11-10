# Simulation & Evaluation Plan

Date: 2025-??-??
Status: Draft — roadmap Phase 3 owner document.

## Objectives
- Extend deterministic playback engine with stochastic modules (downtime, weather, landing congestion).
- Support shift-level playback with aggregation to day/week calendars and blackout reporting (align with Phase 2 shift-based scheduling initiative).
- Expand KPI reporting (cost, utilisation, lateness, mobilisation spend) with configurable outputs (CSV, parquet, dashboards).
- Integrate with Nemora outputs for joint scenario analysis.

## Work Items
- [ ] Audit existing evaluation pipeline (`fhops/eval` → future `evaluation/playback`).
- [ ] Design stochastic sampling API (RNG seeding, scenario ensembles).
- [ ] Implement shift-aware KPI calculators with unit tests and docs.
- [ ] Capture mobilisation-related metrics and reporting hooks.
- [ ] Prototype Nemora integration (import stand tables as stress tests).

### Deterministic Playback Inventory — 2025-02-??
- **Current assets**
  - Legacy `fhops.eval.kpis` simply re-exports `fhops.evaluation.metrics.kpis.compute_kpis`; the latter is still the working KPI entry point (expects a day-level assignments `DataFrame` with `machine_id`, `block_id`, `day` columns).
  - `Scenario` contracts expose `timeline`, `calendar`, and optional `shift_calendar` fields plus `TimelineConfig`/`ShiftDefinition`/`BlackoutWindow` models in `fhops.scheduling.timeline` for describing shift structures.
  - Heuristic solvers (`fhops.optimization.heuristics.sa`) emit `Schedule.plan` dictionaries keyed by `(day, shift_id)` and already consult blackout windows + shift availability, so raw schedule data is available for playback.
- **Gaps to close**
  - `fhops.evaluation.playback` is an empty namespace; there is no deterministic playback engine to transform solver outputs into time-indexed records or to stitch together shift/day aggregates.
  - No bridge converts `Schedule.plan` (or MIP outputs) into the tabular format consumed by `compute_kpis`; downstream consumers hand-roll conversions in notebooks/tests.
  - CLI layer lacks a playback/evaluation command; documentation only references KPI helpers via solver examples.
  - Reporting primitives stop at day-level metrics—no shift/day rollups, blackout reporting, or mobilisation timelines exist.
  - Regression coverage is limited to KPI calculators; there are no fixtures validating end-to-end playback or ensuring calendars/timelines are honoured.
  - Deprecation warning for `fhops.eval.kpis` remains—needs removal once new playback module lands to avoid dual entry points.

### Shift/Day Reporting Specification — 2025-02-??
- **Scope & outcomes**
  - Produce a deterministic playback module that converts solver outputs (`Schedule.plan`, MIP assignment tensors, CSV fixtures) into canonical, shift-indexed records.
  - Emit both shift-granular and day-aggregated datasets consumable by KPI calculators, dashboards, and upcoming stochastic sampling hooks.
  - Define schemas so CLI/reporting layers can stream results to CSV/Parquet and hand-roll aggregations disappear from examples/tests.
- **Input expectations**
  - Accept `Problem` + schedule-like payloads (either `Schedule` or wide DataFrame) with optional mobilisation and shift calendar context.
  - Normalise availability signals: honour `scenario.shift_calendar` when present, fall back to `TimelineConfig.shifts`, and inject synthetic `shift_id="S1"` when neither is provided.
  - Capture blackout usage by inspecting `TimelineConfig.blackouts` and tagging resulting playback rows with `blackout_hit` flags.
- **Proposed output models**
  - `PlaybackRecord`: dataclass capturing `day`, `shift_id`, `machine_id`, `block_id`, `hours_worked`, `production_units`, `mobilisation_cost`, `blackout_hit`, `notes`. Records will be streamable as a generator for large scenarios.
  - `ShiftSummary`: aggregation keyed by `day`, `shift_id`, `machine_id` with totals for production, mobilisation, idle hours, blackout conflicts, sequencing violations.
  - `DaySummary`: aggregation keyed by `day`, grouped across machines, reporting completed blocks, mobilisation totals, downtime reasons, utilisation ratios.
  - Provide adapters to `pandas.DataFrame` so `compute_kpis` can continue to operate while new KPI modules iterate towards shift-aware variants.
- **Data contract additions**
  - Extend `ShiftDefinition` with optional `start_offset_hours` (default 0) to support chronological ordering and downstream charting; mark backwards-compatible.
  - Add `TimelineConfig.reporting_template` stub (enum: `shift_only`, `shift_and_day`, `day_only`) to steer default playback exporters and CLI printing.
  - Track expected mobilisation units on a per-shift basis by adding `mobilisation_cost_flat` vs. `mobilisation_cost_variable` fields to `ShiftSummary` schema.
- **CLI & docs**
  - Introduce `fhops eval playback` command: loads scenario + assignments, runs playback, writes `--shift-out`/`--day-out` files (CSV by default, Parquet optional via flag).
  - Update `docs/howto/evaluation.rst` with usage examples, schema tables, and troubleshooting (e.g., missing shift calendars).
  - Add quickstart snippet demonstrating CLI usage + notebook-friendly Pandas interop.
  - Provide aggregation recipe showing how to summarise per-machine/per-day stats for KPI expansion modules.
- **Testing & validation**
  - Regression fixtures: deterministic playback for `examples/minitoy` and regression scenario; assert shift/day outputs and mobilisation tagging.
  - Property-based tests ensuring aggregation across shifts equals day totals and respects blackout windows (no work counted inside blackout).
  - CLI smoke test invoking `fhops eval playback` with synthetic assignments verifying file emission + console summary.
- **Open decisions**
  - Whether to persist playback outputs inside telemetry store alongside solver metadata (tie-in with tuning framework).
  - How to surface partially assigned shifts (e.g., empty shift_id) — consider dedicated `unassigned` bucket vs. omission.

### Playback Migration Checklist — 2025-02-??
- **Module scaffolding**
  - [x] Create `fhops/evaluation/playback/core.py` containing deterministic playback runner + record dataclasses.
  - [x] Add bridge helpers (`fhops/evaluation/playback/adapters.py`) translating `Schedule.plan` and MIP tensors into canonical playback records.
  - [x] Wire `fhops.evaluation.__init__` exports to include new playback entry points.
  - [x] Capture idle hours and sequencing violation metadata during playback record/summarisation.
- **CLI integration**
  - [x] Implement `fhops eval playback` command (Typer) with `--shift-out`, `--day-out`, `--include-idle` flags and console summary scaffolding.
    - Added stochastic toggles (`--samples`, downtime/weather, landing) with regression coverage in `tests/test_cli_playback.py`.
    - Extend export options to Parquet (when dependencies exist) and Markdown summaries so analytics consumers can grab shareable artefacts.
  - [ ] Update CLI docs (`docs/reference/cli.rst`, `docs/howto/evaluation.rst`) with command usage and schema tables.
  - [ ] Add quickstart snippet illustrating playback → KPI pipeline in `docs/howto/evaluation.rst`.
- **Deprecations & cleanup**
  - [ ] Replace `fhops.eval.kpis` shim with warning-free import once playback module lives under `fhops.evaluation`.
  - [ ] Sweep notebooks/tests to use new playback adapters instead of ad-hoc DataFrame construction.
  - [ ] Document migration guidance in changelog + roadmap when rollout completes.
- **Testing & fixtures**
  - [ ] Author deterministic playback regression fixtures (`tests/fixtures/playback/minitoy.json`, etc.).
    - Proposed approach: use `fhops eval playback` to capture `shift`/`day` CSVs for `examples/minitoy` and `examples/med42`, store under `tests/fixtures/playback/`, and add a regression test that replays the fixtures via `run_playback` to catch schema/metric drift.
  - [ ] Add unit tests covering Schedule→record conversion, blackout tagging, mobilisation accumulation.
    - Added initial coverage in `tests/test_playback.py` verifying block completions, sequencing violations, and idle-hour aggregation on regression scenario data.
  - [x] Add CLI smoke test invoking playback command on synthetic assignments ensuring file creation + summaries (`tests/test_cli_playback.py`).
  - [ ] Ensure property-based tests enforce shift totals == day totals and respect blackout constraints.
  - [ ] Add regression tests comparing CLI exports with expected shift/day schemas once Parquet support lands.

### Stochastic Sampling API Plan — 2025-02-??
- **Objectives**
  - Layer stochastic extensions (downtime, weather, landing congestion) atop the deterministic playback runner with reproducible sampling.
  - Support ensemble execution (N samples per scenario) with aggregated KPI outputs and confidence interval reporting.
- **Core abstractions**
  - `SamplingContext`: dataclass capturing RNG seed, sample_id, scenario metadata, and reusable random streams (downtime, weather, mobilisation).
  - `StochasticEvent`: protocol for sampling events; concrete implementations (`DowntimeEvent`, `WeatherShiftEvent`, `LandingConstraintShock`) mutate playback records prior to aggregation.
  - `PlaybackEnsemble`: orchestrator that runs deterministic playback per sample, applies stochastic events, and emits shift/day summaries + aggregate statistics.
  - Configuration surfaced via Pydantic models (`DowntimeEventConfig`, `WeatherEventConfig`, `LandingShockConfig`, `SamplingConfig`) under `fhops.evaluation.playback.events`.
  - Implemented initial `DowntimeEvent`, `WeatherEvent`, and `LandingShockEvent` logic in `fhops.evaluation.playback.stochastic` with ensemble runner + regression tests.
- **API surface**
  - `run_stochastic_playback(problem, schedule, *, samples=10, seed=123, events=None)` returning `EnsembleResult` with:
    - `sample_records`: iterator/generator of per-sample playback outputs.
    - `aggregated_shift`/`aggregated_day`: DataFrames summarising means/percentiles.
    - `kpi_distribution`: dictionary containing per-KPI arrays + summary stats.
  - CLI entry (`fhops eval simulate`) with flags `--samples`, `--seed`, `--include-downtime`, `--include-weather`, `--include-landing`, `--out-dir`.
- **Sampling mechanics**
  - Introduce RNG utilities under `fhops.evaluation.playback.random` using `numpy.random.Generator`.
  - Provide event-specific configuration (e.g., downtime mean duration, weather severity) via YAML/JSON schema validated against `pydantic` models.
  - Ensure deterministic replay by exposing `--sample-ids` and capturing seed metadata in output manifests.
- **Outputs & storage**
  - Emit ensemble results to structured directory: `out_dir/{sample_id}/shift.csv`, `day.csv`, plus `aggregates/*.csv`.
  - Produce summary manifest (`manifest.json`) capturing configuration, seeds, runtime, KPI summary.
  - Integrate with telemetry store so hyperparameter tuning can reuse stochastic runs.
- **Testing strategy**
  - Unit tests for each event type (downtime/weather/landing) verifying statistical properties via fixed seeds.
    - Added initial coverage in `tests/test_stochastic_playback.py` for downtime, weather, and landing shocks.
  - Property-based tests ensuring deterministic playback equivalence when events are disabled (`samples=1`, no events).
    - Added regression/property checks ensuring base playback is recovered when probabilities are zero and sample production stays within deterministic bounds.
  - Performance smoke to confirm ensemble scaling (e.g., 20 samples on minitoy executes within target wall time).
- **Open questions**
  - Do we require parallel execution support out of the gate (thread/process pools)?
  - How to surface user-defined stochastic events (plugin entry points or config-driven expressions)?

## Testing Strategy
- [ ] Regression fixtures representing deterministic and stochastic runs.
- [ ] Property-based checks to ensure KPIs remain within expected bounds.

## Documentation
- [ ] Author Sphinx how-to for evaluation workflows.
- [ ] Provide notebook-style examples demonstrating robustness analysis.

## Open Questions
- How to manage runtime for Monte Carlo simulations in CI?
- Should KPI outputs support plugin architecture for custom metrics?
# Scenario & Solver Benchmarking Plan

## Phase 2 Kickoff (2025-11-XX)
- **Objective:** Establish a repeatable harness that measures MIP + SA performance across the
  bundled scenarios (`examples/minitoy`, `examples/med42`, `examples/large84`) and captures
  core metrics (build/solve time, objective components, KPI outputs).
- **Deliverables:**
  1. CLI/automation entry-point (e.g., `fhops bench`) running the benchmark suite.
  2. Structured outputs (CSV/JSON) with solver timings and KPI snapshots stored under
     `tmp/benchmarks/` (configurable) plus regression-friendly fixtures for lightweight CI.
  3. Documentation covering how to run the harness and interpret results (`docs/howto/benchmarks.rst`
     or quickstart addendum).
  4. Notes summarising benchmark expectations and follow-up tasks (calibration, regression guards).
- **References:** `notes/metaheuristic_roadmap.md`, `notes/mip_model_plan.md`,
  `docs/howto/quickstart.rst`, `examples/*`.

## Outstanding Tasks
- [x] Requirements sweep (collect expectations from roadmap notes, confirm metrics/KPI coverage).
- [x] Scaffold harness script/module with CLI integration.
- [x] Implement JSON/CSV result emission + optional baseline fixture.
- [x] Add documentation section describing usage.
- [x] Add pytest smoke (marked `benchmark`) for minitoy harness run.
- [x] Update roadmap + changelog upon completion.
