# FHOPS 1.0.1 maintenance plan (Phase 8)

> Parent issue: #90. Feature branch: `feature/phase8-v101-maintenance` (cut from tag `v1.0.0`).
> Children: #91 (8.1 initial state), #92 (8.2 rolling carry-forward), #93 (8.3 playback events),
> #94 (8.4 work units docs), #95 (8.5 SoftwareX playback figure/assets), #96 (8.6 release + forward-port).
> Trigger: SoftwareX R2 review of the FHOPS manuscript (UBC-FRESH/fhops-manuscript#20).

## Problem statement (verified against `v1.0.0`)

### Rolling horizon (`src/fhops/planning/rolling.py`)
`notes/rolling_horizon_plan.md` marks "scenario slicer that trims calendars, demand, and mobilisation
state" and "lock-in tracker ... apply as boundary conditions" as done, but no state is carried
between windows:

1. `_filter_and_rebase_blocks` keeps every block's full `work_required`, so each window re-plans
   volume already delivered in locked days, including finished blocks.
2. Staged inter-role inventory restarts at zero in every window (MILP `inventory_start == 0` at
   the first slot; `SequencingTracker.role_inventory` starts empty). Upstream role progress
   (`role_remaining`) and head-start shift counts (`role_counts_total`) are not carried.
3. No initial machine position, so first-slot moves in a window are free in the solve but
   charged in stitched playback.
4. User `Scenario.locked_assignments` are lost: hooks overwrite them with `[]` in iteration 0,
   and slices ignore them from iteration 1. The operational MILP builder
   (`model/milp/operational.py`) ignores locks entirely.
5. `ScheduleLock` has no `shift_id`; hooks drop `shift_id` and `production`, producing duplicate
   `(machine, day)` locks in multi-shift scenarios.
6. `Scenario.timeline` (blackouts) is not rebased into window coordinates.
7. SA hook `runtime_s` is always `None`; the MILP hook's default `solver="auto"` is passed to
   `SolverFactory` unchanged.

### Stochastic playback (`src/fhops/evaluation/playback/stochastic.py`, `events.py`)
8. `LandingShockEvent` decrements `remaining` per assignment row, not per day; shocks only hit
   the first rows of the horizon.
9. `DowntimeEvent` ignores `mean_duration_hours`/`std_duration_hours`; a whole shift is always lost.
10. `WeatherEvent.correlated_days` is unused (`impact_window_days` already models multi-day spells).

### Contract docs
11. `Block.work_required` is documented as generic work units (e.g. machine-hours), but loader
    batching, playback, KPIs and all reference datasets treat it as volume (m³).

## Design

### 8.1 Optional `Scenario.initial_state` (#91)
New optional, backward-compatible contract section. When absent, every solver, tracker and
playback path must behave **exactly** as in v1.0.0 (regression-tested on reference scenarios).

```python
class BlockInitialState(BaseModel):
    block_id: str
    role_remaining: dict[str, float] = {}   # role -> output still allowed (W_b minus cumulative role output)
    staged_inventory: dict[str, float] = {} # role -> volume output by that role, not yet consumed downstream
    role_shift_counts: dict[str, int] = {}  # role -> shifts already worked (head-start accounting)

class MachineInitialState(BaseModel):
    machine_id: str
    last_block_id: str | None = None        # block the machine occupied in the last worked slot

class ScenarioInitialState(BaseModel):
    blocks: list[BlockInitialState] = []
    machines: list[MachineInitialState] = []

Scenario.initial_state: ScenarioInitialState | None = None
```

Semantics:
- **Remaining terminal volume** is expressed through `Block.work_required` itself; the rolling
  slicer sets it to the remaining volume. Finished blocks are kept with `work_required = 0`, so
  block ids stay valid for mobilisation distances and as `last_block_id` targets.
- Validation: ids must exist; values are non-negative; `role_remaining`/`staged_inventory` keys
  must be roles of the block's harvest system; `last_block_id` must be a scenario block.
- **Heuristics / `SequencingTracker`**: initialise `role_remaining`, `role_inventory` (keyed
  `(block, role)` = output of that role), and `role_counts_total` from the initial state; greedy
  seed, repair, and `evaluate_schedule` use the same initial values; per-machine `previous_block`
  starts at `last_block_id`, so the first move is charged.
- **Operational MILP**:
  - E7: `inventory_start` at the first slot equals the initial staged inventory available to role
    `r` (min over its upstream roles' `staged_inventory`, matching the tracker's min rule; equal to
    the single upstream value for linear chains). The head-start comparison at the first slot uses
    the same quantity instead of 0.
  - E6: add a boundary-transition term for the first slot. For a machine with `last_block_id = b0`,
    charge `ω_mob·δ(m,b0,b) + ω_trans·[b ≠ b0]` on `x[m,b,first_slot]`, as a linear objective term.
  - The formulation docs (OBJ/E6/E7 and the shared TeX/RST include) are updated; defaults
    reproduce the v1.0.0 equations exactly.
- **Locks in the operational MILP**: enforce `Scenario.locked_assignments` as in the older builder.
  A lock without `shift_id` fixes every available shift of that day to the locked block and the
  other blocks to 0; a lock with `shift_id` fixes only that slot.
- `ScheduleLock` gains `shift_id: str | None = None` (backward compatible).

#### 8.1 implementation status and deviations (#91, branch `issue-91-initial-state-contract`)
Implemented as designed, with these additions/deviations:
1. **MILP `role_remaining` cap (addition).** `role_remaining` is honoured by the MILP too:
   `model.role_remaining_cap` adds `Σ_s z[r,b,s] ≤ R_{r,b}` for pairs supplied by the initial state
   (no constraint otherwise), so MILP schedules replay consistently with the tracker.
2. **Locks as equality constraints.** `model.locked_assignment` uses equality constraints rather
   than `Var.fix()` so warm-start seeding cannot overwrite them; incumbents are overlaid with locks
   before seeding. Unavailable locked slots (shift *or* day calendar) are pinned to 0. The legacy
   `optimization/mip/builder.py` keeps `fix()` but is now shift-aware, and warns (`UserWarning`)
   that it ignores `initial_state`.
3. **Shift locks in heuristics.** `OperationalProblem.lock_for(machine, day, shift)` combines
   day-level (`locked_assignments`) and shift-level (`locked_shift_assignments`) locks; greedy seed,
   repair, sanitizer, `evaluate_schedule`, the operator registry, and the MILP warm-start tracker
   use it. Validation rejects unknown shift labels, duplicate `(machine, day, shift)` locks, and a
   day-level lock mixed with shift-level locks for the same machine/day.
4. **Role-keyed state requires `harvest_system_id`.** The tracker ignores roles on blocks without an
   explicit system while the MILP applies the registry's default system, so role-keyed initial state
   on such blocks would be ambiguous; validation rejects it. Role keys are normalised like machine
   roles.
5. **Boundary move semantics.** The MILP charges the boundary move only when the machine works in
   the first slot (its slot-to-slot `y` variables already ignore idle gaps); the heuristics and
   playback charge it on the machine's first *worked* slot. Identical when the machine works the
   first slot (tested); documented in `docs/howto/data_contract.rst`.
6. **Formulation assets.** `scripts/check_formulation_assets.py` and the OBJ/E6/E7 labels live only
   on `main` (Phase 5, #64/#65); on the 1.0.1 line the canonical source is
   `docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md`, rendered by
   `docs/softwarex/manuscript/scripts/export_docs_assets.py`. Pandoc **3.6** reproduces the
   committed v1.0.0 TeX/RST byte-for-byte (3.1.3, pinned on `main`, changes RST list indentation),
   so assets were regenerated with 3.6. The forward-port (#96) must apply the same terms to the
   labelled OBJ/E6/E7 blocks on `main`.
7. **Bundle serialisation.** `OperationalMilpBundle` carries `locked_assignments` and `initial_*`
   mappings; `bundle_to_dict` emits them only when non-empty, so v1.0.0 dumps are unchanged and old
   dumps still load.
8. **Regression evidence.** `tests/initial_state/test_v100_regression.py` compares against
   baselines captured on unmodified v1.0.0 code (`tests/fixtures/v100_regression/`): SA tiny7
   (seed 123, 300 iters) objective `4306.522752000001` + assignments, SA med42 (seed 7, 150 iters)
   objective `-38434.22731600001` + assignments, operational MILP tiny7/HiGHS objective
   `4388.082751999992` (±1e-6), and playback KPIs for the three assignment tables (exact).

Observed pre-existing issues (not changed here): `solve_operational_milp(..., incumbent_assignments=...)`
with `solver="highs"` raises `TypeError` (`LegacySolverWrapper.solve()` rejects `warmstart`; fixed in 8.7, #99);
`load_scenario` attaches YAML `locked_assignments` via `model_copy`, so they skip cross-validation
(fixed in 8.8, #100).

### 8.2 Rolling carry-forward (#92)
After each iteration locks its leading days:
1. Replay the stitched locked plan against the **base** scenario with the sequencing tracker
   (`assignments_to_records(...)` → `it.sequencing_tracker`) for days `< next_start`, using the
   same deterministic production rule as playback.
2. Build the next window's state from the tracker:
   - `work_required` = `remaining_work[b]` (terminal volume still to deliver);
   - `role_remaining`, `staged_inventory`, `role_shift_counts` per block;
   - `last_block_id` = each machine's last locked assignment (chronological by day, shift).
3. Slice the base scenario for the next window (calendars, shift calendar, **timeline/blackouts**,
   block windows, production rates, mobilisation), apply the state, and merge **user locks**
   (rebased) with any carried locks. Hooks merge locks instead of overwriting them.
4. Locks keep `shift_id`; `_lift_locks_to_base` preserves it.
5. Hook telemetry: SA records wall-clock `runtime_s`; MILP `solver="auto"` resolves to the default
   operational solver (HiGHS) explicitly.
6. Acceptance tests:
   - On a scenario that finishes a block in window 1, window 2 has that block at
     `work_required = 0` and no new assignments to it.
   - The state passed to window k equals a fresh tracker replay of the stitched plan up to k.
   - Single-window rolling (`sub_days = lock_days = master_days`) matches a direct solve.
   - Stitched-plan KPIs (`compute_rolling_kpis`) never over-count delivered volume.
   - User locks survive all iterations.
   - Blackouts land on the correct rebased days.
7. Docs: `docs/howto/rolling_horizon.rst` describes the carried state and its evaluation;
   `notes/rolling_horizon_plan.md` checkboxes are corrected.

#### 8.2 implementation status and deviations (#92, branch `issue-92-rolling-carry-forward`)
Implemented as designed (`carry_forward_state`, `RollingCarryState`, `slice_scenario_for_window(...,
carry_state=)`), with these decisions/deviations:
1. **Replay production rule.** The replay uses the playback rule (`min(rate, block remaining)`
   capped by the tracker), not the MILP's planned `prod`. `ScheduleLock` carries no production, and
   `compute_rolling_kpis` evaluates the same lock table with the same rule, so carried state and
   stitched KPIs agree by construction (tested: final `remaining_work` = KPI
   `remaining_work_total`). Consequence: the MILP's same-day shift-to-shift inventory use is not
   reproduced by the tracker (next-day availability), which shows up as playback sequencing
   violations on multi-shift MILP plans (pre-existing, also for full-horizon plans).
2. **Omission rules.** `staged_inventory` omits zeros **and terminal roles** (the tracker books
   terminal output into `role_inventory`, but it is delivered volume with no downstream consumer);
   `role_remaining` omits values equal to the window's `work_required` (contract default; this also
   means no MILP `role_remaining_cap` for such roles, as in a fresh scenario); counts omit zeros.
   Volumes `<= 1e-6` are zeroed (tracker `BLOCK_EPSILON`).
3. **Shift order.** `last_block_id` uses `(day, shift_id)` lexicographic order (missing shift →
   `S1`), the same order the MILP slot list, heuristics, and playback use.
4. **Block filtering kept.** Blocks whose time window does not overlap a window are still dropped
   (a zero-work placeholder could not be made unavailable within contract validation). A carried
   `last_block_id` pointing to a dropped block is removed with a warning in
   `RollingPlanResult.warnings`; a user lock targeting a dropped block raises
   `RollingInfeasibleError`.
5. **Slices are re-validated** (`Scenario.model_validate`), so merged locks get full
   cross-validation; hooks also merge + re-validate and no longer mutate the scenario they receive.
6. **Telemetry addition.** `RollingIterationSummary.remaining_work_start` (also in
   `summarize_plan`/CLI exports); `MILPSolver.requested_solver` keeps the user value while
   `MILPSolver.solver`/metadata `mip_solver` report the resolved backend.
7. **MILP hook drops `assigned = 0` rows** (the driver also emits rows with production but no
   assignment flag); v1.0.0 turned them into locks.
8. **Time-limited MILP windows** depend on the 8.7 driver change (#99/#102) that keeps
   limit-stopped incumbents. Before it, `maxTimeLimit` returned an empty schedule and 30 s/window
   MIP rolling runs on ka_6 locked nothing in three of four windows (found during the #92 sanity
   check; an equivalent local fix was dropped when rebasing onto 8.7).

Observed pre-existing issues (not changed here): `compute_kpis` on an **empty** assignment table
reports `total_production = Σ work_required` (playback has no tracker, `remaining_work_total`
defaults to 0) — the v1.0.0 "MIP baseline delivered 30913 m³" on ka_6 is this artefact of an empty
(time-limited) plan; the operational MILP ignores `timeline.blackouts`; window objectives have no
end-of-window value for staged inventory, so windows shorter than the harvest pipeline can plan no
upstream work (tiny7 MILP 7/3/1).

### 8.3 Playback event fixes (#93)
- Landing shocks: for each landing and each day, a shock starts with `probability`, lasts
  `duration_days` calendar days, and scales production of every assignment on that landing on the
  affected days by a sampled multiplier. Overlapping shocks take the minimum multiplier.
- Downtime: for each selected machine-shift, sample a duration ~ Normal(mean, std), truncated to
  `[0, shift_hours]`, and remove the fraction `duration/shift_hours` of that assignment's production.
  A full-shift loss still sets `assigned = 0`. `shift_hours` comes from the shift definition
  (fallback: machine `daily_hours`/shifts per day). Downtime-hours KPIs use the sampled hours.
- `WeatherEvent.correlated_days`: deprecated. Emit a `DeprecationWarning` when it is set
  explicitly; behaviour is unchanged (`impact_window_days` models spells).
- Update tests that pin stochastic numbers; add tests for each corrected semantic.

**Implementation notes (#93, branch `issue-93-playback-event-fixes`):**
- Landing shocks sample over the full scenario horizon (`1..num_days`), landing-major then
  day-ascending: one `rng.random()` per landing-day, plus one `rng.uniform` per started shock.
  New helper `LandingShockEvent.sample_multipliers()` returns the `(landing, day) -> multiplier` map.
- Downtime keeps the v1.0.0 selection rule (per day: `rng.choice` of exactly
  `min(max_concurrent, n)` rows when `max_concurrent` is set, otherwise one `rng.random()` per row),
  then one `rng.normal` per selected row. "Truncated" is implemented as **clipping** to
  `[0, shift_hours]` (censoring, one draw per hit), so a full-shift loss has positive probability;
  `d == 0` leaves the row untouched.
- `shift_hours` deviation: deterministic playback records `hours_worked` as the timeline shift
  hours, else the machine `daily_hours` (no division by shifts per day). Downtime uses the same
  shared resolver (`adapters.shift_hours_resolver`) so sampled downtime and recorded hours stay on
  one scale; the two rules differ only for multi-shift scenarios without `timeline.shifts`, where
  playback itself already reports `daily_hours` per shift (left unchanged; out of scope).
- Downtime KPIs: in v1.0.0 downtime rows were filtered out (`assigned = 0`) before records were
  built, so `downtime_hours_total` was always 0. Rows flagged by downtime now always yield a
  record: cancelled shifts emit `production = 0`, `hours_worked = 0`, `downtime_hours = shift_hours`
  and bypass the sequencing tracker and mobilisation costing (same delivered volume as before);
  partial losses report `hours_worked = shift_hours - d`. `PlaybackRecord.downtime_hours` is new.
- Event composition: weather and landing shocks now multiply the row's *current* production
  instead of overwriting it from the deterministic baseline (otherwise partial downtime would be
  erased by a later weather/landing event). Results are identical when a single event is active.
  Cancelled rows are skipped by weather/landing.
- `correlated_days`: `model_validator(mode="after")` warns when `"correlated_days" in
  model_fields_set`. `sampling_config_for()` (synthetic tiers) drops the field before its
  dump/re-validate round trip so it does not warn spuriously.
- CLI: new `--downtime-mean` / `--downtime-std` options (defaults 4.0 / 1.5 h, matching
  `DowntimeEventConfig`); help text for downtime/landing/weather flags updated.
- `test_kpi_stochastic_snapshot` fixture regenerated (`tests/fixtures/kpi/stochastic.json`).

### 8.4 Units docs (#94)
`Block.work_required` documented as m³ (terminal delivered volume) in the contract docstring,
data-contract docs, and the loader/playback docs; no behaviour change.

**Implementation notes (#94, branch `issue-94-work-required-units`):** `Block`, `ProductionRate`,
`ObjectiveWeights` and `Scenario.production_rates` docstrings/inline comments now state m³ (rates
in m³ per shift assignment); `docs/howto/data_contract.rst` (blocks/production-rate notes),
`docs/howto/evaluation.rst` (KPI units), and `docs/howto/system_sequencing.rst` (example comment)
updated; `compute_kpis`, `SequencingTracker`, `PlaybackResult`, `OperationalMilpBundle` and
`SyntheticDatasetConfig` docstrings document the m³ convention. `PlaybackRecord`/
`assignments_to_records` m³ notes land with #93 to avoid overlapping hunks. The formulation
includes already describe `W_b` as volume and were left untouched (no asset regeneration).

### 8.5 SoftwareX figure and assets (#95)
- `docs/softwarex/manuscript/scripts/plot_playback_variability.py`: column-width figure size,
  ≥ 9 pt fonts at print size, legend inside the canvas (no clipping, no suptitle), upper-case
  solver labels.
- Regenerate playback assets with the fixed events (`run_playback_analysis.py`) and record the
  benchmark log. Deterministic benchmark/tuning/scaling assets must be unchanged.

**Implementation notes (#95, branch `issue-95-playback-figure`):**
- Figure: 3 panels, one legend row above them (`fig.legend(loc="outside upper center")` with
  constrained layout, saved with `bbox_inches="tight"` + `bbox_extra_artists`), no suptitle,
  upper-case SA/ILS ticks, y label "Mean day-level utilisation", 9 pt text everywhere, error bars
  only on the stochastic bars (population std over the 50 samples), PNG at 300 dpi plus PDF
  (PDF `CreationDate` dropped so reruns are byte-identical).
- **Deviation (size):** the issue asked for ~6.5 in. The manuscript (`elsarticle`
  `preprint,review,12pt`) has `\linewidth` = 390 pt = 5.4 in, measured from the R1 PDF (the old
  figure is placed 5.396 in wide). A 6.5 in figure would be scaled to 83% and 9 pt text would print
  at ~7.5 pt. The figure is drawn at 5.35 × 2.4 in instead (saved 5.30 × 2.33 in), so
  text prints at ≥ 9 pt in the review PDF and only grows in a wider journal layout.
- Playback regenerated with `run_playback_analysis.py` (unchanged `STOCHASTIC_FLAGS`; downtime
  durations now use the `eval-playback` defaults of 4 h mean / 1.5 h std, documented in the
  script). The script now calls `sys.executable`, writes `metrics.json` and `summary.md` with a
  trailing newline (the committed copies had been normalised by the end-of-file-fixer hook), and
  documents that `tabulate` must be installed (otherwise `summary.md` falls back to CSV blocks).
  A second run into a temp directory was byte-identical.
- Deterministic playback is byte-identical except `med42/ils/deterministic`. The committed copy
  was stale: it came from an earlier ILS assignment set. Mobilisation $10,662.28 vs $10,682.68 in
  the committed `benchmarks/med42/summary.csv`; v1.0.0 code reproduces the new file from the
  committed `ils_assignments.csv`. Utilisation is unchanged (0.5635, same 213 shifts); production
  and mobilisation now match the benchmark assignments.
- Stochastic utilisation drops less than in v1.0.0 because a downtime hit now loses ~4 h of a
  24 h shift (≈ 0.05 × 4/24 ≈ 0.8% of hours) instead of the whole shift (5%); weather and landing
  shocks scale production, not hours.
- SA reproducibility under the maintenance branch: tiny7 (SA default/diversify/mobilisation,
  8000 iters, seed 42; ILS 1500 iters, batch 4, workers 12) and small21 (SA 4000 iters, seed 42,
  three presets) re-solved in `/tmp/opencode/pb95-bench`: objective, assignments, production,
  mobilisation, completed blocks and day utilisation match the committed `summary.csv` exactly and
  every assignment CSV is byte-identical (details in CHANGE_LOG #95). No committed MILP row exists.
- `benchmark_runs.log` entry is a partial regeneration (playback only) with a `note:` line.

### 8.6 Release and forward-port (#96)
Version `1.0.1`; release notes in `docs/releases/v1.0.1.md`; Hatch build, clean-venv smoke,
TestPyPI → PyPI, annotated tag `v1.0.1`, GitHub release. Forward-port the fixes to `main` (next
1.1.0 alpha) via a PR, resolving ROADMAP/CHANGE_LOG conflicts.

### 8.7 MILP warm start with HiGHS (#99)
Problem: `solve_operational_milp(..., incumbent_assignments=...)` passed `warmstart=True` to
`SolverFactory("highs")`, which on Pyomo ≥ 6.9 (venv: Pyomo 6.10.1, highspy 1.15.1) is the
`pyomo.contrib.solver` HiGHS wrapped in `LegacySolverWrapper`; its `solve()` has no `warmstart`
keyword (`TypeError`) and the interface has no MIP-start support at all.

Fix (branch `issue-99-highs-warm-start`, `src/fhops/model/milp/driver.py`):
1. Seeded `highs`/`appsi_highs` solves use `SolverFactory("appsi_highs")` with `warmstart=True`;
   APPSI's `Highs._warm_start` passes every seeded value to `highspy.Highs.setSolution`.
   Unseeded solves still use `highs` (v1.0.0 regression baselines unchanged).
2. The APPSI solve uses `load_solutions=False` + `opt.load_vars()` (APPSI raises when asked to
   load a missing solution) and routes the HiGHS log to a private logger; the lines about the MIP
   start become `result["warm_start"]["solver_messages"]` and `accepted` (`True` on
   `MIP start solution is feasible`, `False` when the completion LP is infeasible, else `None`).
3. Legacy plugins with `warm_start_capable()` (Gurobi, CBC ≥ 2.8, CPLEX, …) keep receiving
   `warmstart=True`; everything else (including other `LegacySolverWrapper` solvers) solves
   without the start and emits `MilpWarmStartWarning`.
4. A solve stopped by a limit (`maxTimeLimit`, `maxIterations`, `maxEvaluations`,
   `objectiveLimit`) that holds a feasible incumbent now reports it (objective + assignments)
   instead of `objective=None`; otherwise a time-limited warm start would discard the very
   incumbent it was given. This also applies to unseeded time-limited solves.
5. CLI prints `Warm start: method=… (accepted|rejected|status unknown)` plus the HiGHS lines, and
   telemetry stores the dict under `extra.warm_start`.

Evidence (tiny7): cold HiGHS solve optimal `4388.082751999992`; warm re-solve logs
`MIP start solution is feasible, objective value is 4388.082752` and finishes optimal in ≈0.2 s;
with `time_limit=1e-6` the warm solve still returns the seed (`4388.08…`, `maxTimeLimit`).

Follow-ups (not in this change): the rolling MILP hook does not pass incumbents (rolling.py owned
by #92); ILS "hybrid MIP warm start" calls `solve_mip` without an incumbent; `pyomo.contrib.solver`
interfaces may gain native warm starts (e.g. Gurobi `warmstart_discrete_vars`), at which point
the APPSI route can be revisited.

### 8.8 Validate YAML `locked_assignments` (#100)
Problem: `load_scenario` built the core `Scenario` and then attached every optional YAML/CSV
section (`locked_assignments`, `timeline`, `mobilisation`, `crew_assignments`, `harvest_systems`,
`objective_weights`, `geo`, `road_construction`, `initial_state`) with
`model_copy(update=...)`, which skips Pydantic validators. YAML locks with unknown machines,
blocks, days or shift labels, duplicate locks, day+shift mixes, and locks inside blackout windows
were accepted.

Fix (branch `issue-100-yaml-lock-validation`, `src/fhops/scenario/io/loaders.py`): the core tables
are still validated first (so their errors surface first, unchanged), then the optional sections
are collected and the scenario is re-validated once with `Scenario.model_validate`, so YAML locks
go through exactly the same `Scenario._cross_validate` rules as model-constructed locks (including
the #91 `shift_id` rules and the blackout check), and the other optional sections get the
cross-checks they previously skipped (mobilisation/crew machine and block references,
`initial_state`, which replaces the explicit `validate_initial_state` call). Locks are only
supported inline in YAML (there is no CSV lock table).

Evidence: every repository scenario YAML (17 loadable + 2 intentionally invalid fixtures) and the 9
Jaffray MASc scenarios load to identical `Scenario` objects / identical errors before and after.
`tests/test_scenario_loader_locks.py` covers 10 invalid lock cases (all accepted by the old
loader) plus valid day/shift locks.

Not changed: `Scenario._validate_system_ids` (block `harvest_system_id` vs `harvest_systems`) runs
as a field validator before `harvest_systems` is available in field order, so it still does not
fire for YAML or Python construction; behaviour is unchanged.

### 8.9 KPIs for empty and partial plans (#108)
Problem (pre-existing at v1.0.0, noted in §8.2): `compute_kpis` on an **empty** assignment table
reported `total_production = Σ work_required` and `remaining_work_total = 0` (ka_6: 30913.355595
m³ for a time-limited MIP run with no incumbent). `compute_rolling_kpis` / `evaluate_rolling_plan`
never forwarded an empty frame (empty rolling plans raised `ValueError`, empty baselines were
silently dropped to `baseline_kpis=None`), but any direct `compute_kpis` call (CLI KPI output,
benchmark harness, experiment scripts) was affected.

Root cause: `assignments_to_records` returned a bare `iter(())` for an empty frame, without the
`sequencing_tracker` attribute, so `run_playback` left `remaining_work_total` at its `0.0`
default; `compute_kpis` then set `total_production = Σ work_required − remaining_work_total`
unconditionally. Frames with rows but no `assigned > 0` row already built a tracker and were
correct.

Fix (branch `issue-108-empty-plan-kpis`):
1. `assignments_to_records` always attaches a fresh tracker (empty frames, `None`, or no assigned
   rows) — `run_playback` now always reads `delivered_total`, `remaining_work_total` and
   `sequencing_debug` from the tracker (a missing tracker is a `RuntimeError`).
2. `compute_kpis` uses the playback `delivered_total` as `total_production`; the
   `Σ work_required − remaining` form is only used as a float-tidy replacement when it agrees
   with `delivered_total` (tolerance `max(1e-6, 1e-9 · Σ work_required)`), so non-empty plans keep
   byte-identical KPIs.
3. `compute_rolling_kpis`: an empty rolling plan still raises `ValueError` (deliberately kept from
   v1.0.0 so a failed rolling run cannot be scored silently); an explicitly supplied **empty
   baseline** is now scored as a zero-delivery plan (v1.0.0 silently dropped it and returned
   `baseline_kpis=None`). `baseline_assignments=None` still skips the comparison.

Empty-plan KPI semantics (documented in `compute_kpis`, `docs/howto/evaluation.rst`,
`docs/howto/rolling_horizon.rst`): `total_production = 0`, `remaining_work_total =
staged_production = Σ work_required` of the evaluated scenario (carried-forward volume for a
rolling window; `initial_state` staged inventory does not change it), `completed_blocks = 0`,
`makespan_day = 0` / `makespan_shift = "N/A"`, day utilisation `0`, shift/machine/role
utilisation, mobilisation, downtime and weather keys absent, sequencing counts `0` with every
harvest-system block counted as clean. Stochastic playback of an empty plan reports
`delivered_total = 0` and full remaining work for the base result and every sample.

Audit of the other KPIs for partial plans: production, completion, mobilisation, sequencing,
utilisation, makespan, downtime and weather KPIs are all derived from the playback records or the
tracker and needed no change; for any plan `total_production + remaining_work_total =
Σ work_required`.

Evidence: KPIs for `tests/fixtures/playback/{tiny7,med42,large84}_assignments.csv` and the three
`tests/fixtures/v100_regression` CSVs are byte-identical before/after (JSON dump compare); of the
48 ka_6 assignment CSVs in the read-only Jaffray repo, only the 2 empty ones change
(`ka_6_sub14_lock14_mip_20260305_012750`, `ka_6_sub14_lock14_mip_20260322_010456`: 30913.355595 →
0 m³ delivered). Tests: `tests/test_kpi_empty_plans.py` (15 of 26 fail on the pre-fix code; the
pre-fix KPI snapshot lives in `tests/fixtures/kpi/pre108_snapshot.json`).

Downstream: any Jaffray rolling-horizon result whose MIP baseline (or rolling run) produced an
empty assignment table must be re-evaluated; the old "full-horizon MIP baseline = 30913 m³" figure
is this artefact.

### 8.10 MILP / playback sequencing alignment (#109)
Problem: operational-MILP plans for the Jaffray ka_6 scenario replayed with ~50–130 sequencing
violations (full horizon and rolling 28/14/7) and playback under-reported the MILP's delivered
volume. The issue assumed one shift per day; ka_6 actually has **three timeline shifts per day**
(`S1`–`S3`, 8 h each, 336 slots over 112 days).

Diagnosis (branch `issue-109-milp-playback-alignment`; scripts in `/tmp/opencode/fhops109`:
`diag.py` solve + replay + classify, `fuzz.py` random 2–4-role pipelines solved to optimality,
`roll.py` rolling replay). Root causes, each with a test in
`tests/sequencing/test_milp_playback_alignment.py`:
1. **Release per day vs per slot (E7).** The MILP lets a role use upstream output from the previous
   *shift* (`I_start(s) = I(prev(s))`); `SequencingTracker` and the heuristic repair released staged
   output only at the day roll. This is the **only** class on ka_6: with slot-level release alone,
   7/14/28-day MILP plans replay with 0 violations (20/42/57 before).
2. **Solver noise.** The tracker compared inventories with a 1e-9 m³ tolerance; HiGHS plans miss
   by up to ~5e-7 m³ (e.g. 12.8629995 vs 12.863). Tolerance is now `SEQUENCING_TOLERANCE = 1e-6`.
3. **Loader threshold per machine.** With two loaders in a slot the tracker checked the truckload
   rule against what the first loader left (28.86 < 30 m³); E8 checks the volume staged at the
   start of the slot for the whole role. The tracker/repair now use the slot-start volume.
4. **Head start in shifts vs volume (E8).** The tracker counted upstream/downstream machine-shifts;
   the MILP requires staged volume `B = β × Σ upstream fleet rate`. Shared helper
   `headstart_buffer_volumes`; tracker and repair compare slot-start staged volume with it.
   `initial_state.role_shift_counts` is now informational.
5. **Phantom upstream volume (formulation gap).** Only the terminal role was tied to `W_b`, so MILP
   plans felled/processed more wood than the block holds (ka_6: 6238.6 m³ felled on a 5077.4 m³
   block) and used that volume to meet head-start/loader thresholds (fuzz: a 255 m³ buffer met on a
   112 m³ block). The MILP now caps every role (`Σ_s z ≤ R_{r,b}`, `R = W_b` by default); the
   head-start buffer is waived once every upstream role has output its whole remaining volume
   (binary `upstream_done`, head-start roles only); the loader threshold is
   `min(q_batch, R_{r,b})`. Formulation updated (sets `B^seq`, `P^hs`; parameters `B`, `R`;
   variable `h`; E8; remaining-output cap; "Changes from v1.0.0").
6. **Blocks without `harvest_system_id`.** The MILP applied the registry's default system; the
   tracker/heuristics treat them as unsequenced (documented contract). Playback then delivered more
   than the MILP (fuzz: 19/30 cases). New bundle field `unsequenced_blocks`: no role compatibility,
   no inventory/activation, machine-level production counts (serialised only when non-empty).
7. **Shift order.** The MILP used `Problem.shifts` (timeline definition order) while heuristics and
   playback sorted labels (`day` before `night`). `ordered_shift_keys` (data.py) now defines the
   order everywhere (bundle, `OperationalProblem.shift_keys`, ILS, playback sort, rolling
   `last_block_id`). Identical for single-shift and lexicographically ordered labels.
8. **Rolling replay at the production rate.** MILP rolling locks dropped the planned production, so
   carry-forward and `compute_rolling_kpis` replayed every lock at `min(rate, remaining)`: the
   carried state differed from the plan the next window built on, and full-rate proposals with
   less input were flagged (93 violations on ka_6 28/14/7 even with fixes 1–7).
   `ScheduleLock.production` (optional, ignored by solvers) is now set by the MILP hook and used by
   carry-forward/KPIs; SA locks keep the rate rule.

Not changed (no violations possible): E9 batching (`z = q·n + u` imposes nothing beyond `z ≥ 0`),
role-compatibility vs `forbidden_role`, roles without machines (MILP stricter), landing capacity
(MILP: per day with slack; heuristics: per shift; not a sequencing rule).

Reference ladder: single-slot days, buffers 0, explicit systems; fixes 1–4 are no-ops there.
`fhops bench suite` re-runs (committed flags) for tiny7 (SA ×3, ILS, Tabu) and small21 (SA ×3,
ILS, Tabu) match the committed `summary.csv` and assignment CSVs exactly (see CHANGE_LOG #109);
`tests/initial_state/test_v100_regression.py` (SA tiny7/med42, MILP tiny7 4388.082752) passes.

Trade-offs / follow-ups:
- MILP rolling totals now reflect the window plans: tiny7 7/4/2 and 7/5/3 deliver ≈3.9k of 4.4k m³
  (previously the rate replay credited unplanned upstream work; still the end-of-window valuation
  limitation, 8.2).
- MILP with caps is never less strict than playback at block tails: a loader fleet slower than one
  truckload per shift can leave < `q_batch` per block undelivered.
- Head-start waivers add `|P^hs| × |S|` binaries; an earlier variant that also waived loader
  thresholds found no 28-day ka_6 incumbent in 1200 s with HiGHS, hence loaders use the static
  `min(q, R)` threshold instead.

### 8.11 Timeline blackouts in the operational MILP (#110)
Problem: `Scenario.timeline.blackouts` blocked slots for the heuristics (`OperationalProblem.
blackout_shifts`: repair, greedy seed, sanitizer, `evaluate_schedule` penalty) and were flagged by
playback (`blackout_hit`), but the operational MILP ignored them (evidence: a 2-machine, 2-shift,
4-day scenario with days 2–3 blacked out — the MILP worked all 8 blocked slots, 640 m³; now 0
slots, 320 m³).

Heuristic semantics (kept exactly): fleet-wide, inclusive day windows; for each blackout day and
every machine, the blocked shifts are the machine's `shift_calendar` shifts that day, otherwise
every `timeline.shifts` name, otherwise `S1`. Not per landing or block.

Fix (same branch/PR as #109, separate commit; both touch `model/milp/{data,operational}.py`):
`build_blackout_slots(pb)` in `fhops.model.milp.data` (moved from the private
`_build_blackout_shifts`), stored as `OperationalMilpBundle.blackout_slots` (sorted; serialised
only when non-empty). `OperationalProblem.blackout_shifts` is now `frozenset(bundle.blackout_slots)`
and the MILP's availability check returns 0 for those slots (`machine_capacity` forces
`Σ_b x = 0`; locks in such slots are pinned to 0, and warm-start lock overlays skip them). The
canonical formulation defines `A_{m,s} = 0` in blackout slots. Rolling windows already rebase
blackouts (8.2), so window MILPs now honour them too.

Tests: `tests/model/test_milp_blackouts.py` (slot set = heuristic set, shift-calendar per machine,
bundle round trip, `machine_capacity` bounds, MILP and SA use exactly the open slots, rolling MILP
locks no blackout day).

### 8.13 Heuristics, tracker, and playback fixes from the pre-release audit (#116)
Pre-release antagonistic audit of the 1.0.1 candidate (f31aa65; evidence and repro scripts in
`/tmp/opencode/audit-{3,4}-scratch/`, this branch's scripts in `/tmp/opencode/w116/`). Branch
`issue-116-heuristics-playback-audit`.

**1. Multi-shift heuristic regression since #109 (root cause).** On the Jaffray 3-shift scenarios
(`ka_6`, `pg_6`, `ni_6`, `ka_18`, `pg_18`; landings with `daily_capacity = 2`, heuristics count
machines per landing per *shift*, 1000 per extra machine because `landing_surplus` is weighted 0)
SA/ILS/Tabu objectives dropped versus v1.0.0 purely through more landing-capacity penalties
(delivered volume and sequencing were equal). Ablation on copies of f31aa65
(`/tmp/opencode/w116/mkvar.py`, greedy seed + `evaluate_schedule`):

| Variant of f31aa65 | ka_6 greedy obj / landing penalties | pg_6 |
|---|---|---|
| f31aa65 | −17086.64 / 48 | 22923.96 / 45 |
| repair releases staged output per **day** again (only change) | −6086.64 / 37 | 34923.96 / 33 |
| tracker per day (evaluation only) | −70556.29 / 43 violations | −47035.66 / 55 violations |
| v1.0.0 loader rule in the repair | −17086.64 / 48 | 22923.96 / 45 |
| v1.0.0 | −6086.64 / 37 | 34923.96 / 33 |

Reverting only the repair's per-slot release reproduces v1.0.0 exactly; the loader rule and the
head-start volume (no head starts in these scenarios) are no-ops and the slot order is unchanged
(`S1`–`S3` are defined in label order). Mechanism: neither the greedy seed nor the repair looks at
landing capacity. Under per-day release (v1.0.0) a downstream role could not use output staged
earlier the same day, so the repair dropped/moved most downstream machines away from a block on the
days its upstream roles worked it — accidentally spreading the crew over landings. With per-slot
release (#109, correct per E7) the repair keeps feller, skidder, processor and loader on the same
block in consecutive shifts of one day, i.e. 3–4 machines on a capacity-2 landing per shift.

Fix (heuristics only; `OperationalProblem.multi_shift_days`, `common._repair_schedule_cover_blocks`):
on days with more than one shift slot, and only when `landing_surplus` is weighted 0, the repair
keeps or fills an assignment only if fewer than `daily_capacity` *other* machines are planned on
the block's landing in that shift (other machines count with their current plan, so existing
assignments of machines visited later in the slot keep their position; locked slots are exempt).
Single-shift days are untouched, so the reference ladder is byte-identical. Two alternatives were
measured and rejected: first-come-first-served in role order (upstream roles take the landing;
lower delivered volume on 14/28-day ka_6 windows, e.g. 18424–18770 vs 19084–19556 m³) and a
look-ahead that ignores later machines whose assignment would be dropped (lower on pg_6 28-day
windows: 17089–17616 vs 18910 objective). The chosen rule's objective and delivered volume are
≥ f31aa65 on every truncated-horizon run (ka_6 14/28 d, pg_6/ni_6/ka_18 28 d, SA 500 iterations,
seeds 1–3; `/tmp/opencode/w116/cmp_trunc.py`).

SA, 1500 iterations (`/tmp/opencode/w116/cmp.py`; objective / delivered m³ / playback sequencing
violations / landing-capacity excess in the final plan; "greedy" = seed schedule after repair):

| Scenario | Seed | v1.0.0 | f31aa65 | this branch |
|---|---|---|---|---|
| ka_6 | greedy | -6086.64 / – / – / 37 | -17086.64 / – / – / 48 | 30913.36 / – / – / 0 |
| ka_6 | 1 | 24913.36 / 30913.4 / 0 / 6 | 15913.36 / 30913.4 / 0 / 15 | 30913.36 / 30913.4 / 0 / 0 |
| ka_6 | 2 | 23913.36 / 30913.4 / 0 / 7 | 13913.36 / 30913.4 / 0 / 17 | 30913.36 / 30913.4 / 0 / 0 |
| ka_6 | 3 | 22913.36 / 30913.4 / 0 / 8 | 18913.36 / 30913.4 / 0 / 12 | 30913.36 / 30913.4 / 0 / 0 |
| pg_6 | greedy | 34923.96 / – / – / 33 | 22923.96 / – / – / 45 | 67923.96 / – / – / 0 |
| pg_6 | 1 | 60923.96 / 67924.0 / 0 / 7 | 58923.96 / 67924.0 / 0 / 9 | 67923.96 / 67924.0 / 0 / 0 |
| pg_6 | 2 | 58923.96 / 67924.0 / 0 / 9 | 62923.96 / 67924.0 / 0 / 5 | 67923.96 / 67924.0 / 0 / 0 |
| pg_6 | 3 | 60923.96 / 67924.0 / 0 / 7 | 50923.96 / 67924.0 / 0 / 17 | 67923.96 / 67924.0 / 0 / 0 |
| ni_6 | greedy | -126706.64 / – / – / 230 | -138889.32 / – / – / 248 | 1961.36 / – / – / 0 |
| ni_6 | 1 | 24925.36 / 214508.0 / 0 / 81 | 24189.36 / 217140.0 / 0 / 87 | 113821.36 / 218456.0 / 0 / 0 |
| ni_6 | 2 | 14609.36 / 213850.0 / 0 / 90 | 22189.36 / 217140.0 / 0 / 89 | 112505.36 / 217798.0 / 0 / 0 |
| ni_6 | 3 | 41609.36 / 213850.0 / 0 / 63 | 42873.36 / 216482.0 / 0 / 67 | 111189.36 / 217140.0 / 0 / 0 |
| ka_18 | greedy | -123613.87 / – / – / 195 | -135613.87 / – / – / 207 | 71386.13 / – / – / 0 |
| ka_18 | 1 | -49613.87 / 71386.1 / 0 / 121 | -63613.87 / 71386.1 / 0 / 135 | 71386.13 / 71386.1 / 0 / 0 |
| ka_18 | 2 | -37613.87 / 71386.1 / 0 / 109 | -45613.87 / 71386.1 / 0 / 117 | 71386.13 / 71386.1 / 0 / 0 |
| ka_18 | 3 | -26613.87 / 71386.1 / 0 / 98 | -43613.87 / 71386.1 / 0 / 115 | 71386.13 / 71386.1 / 0 / 0 |
| pg_18 | greedy | -1021173.44 / – / – / 1311 | -1044697.44 / – / – / 1349 | 173999.63 / – / – / 0 |
| pg_18 | 1 | -292768.37 / 432997.0 / 0 / 601 | -271608.37 / 439577.0 / 0 / 593 | 289872.45 / 423817.4 / 0 / 0 |
| pg_18 | 2 | -362716.37 / 431023.0 / 0 / 667 | -275608.37 / 439577.0 / 0 / 597 | 285859.63 / 421811.0 / 0 / 0 |
| pg_18 | 3 | -342084.37 / 432339.0 / 0 / 649 | -299292.37 / 440235.0 / 0 / 622 | 299019.63 / 428391.0 / 0 / 0 |

ILS (100 iterations) and Tabu (1000 iterations), seed 1:

| Scenario | Solver (seed 1) | v1.0.0 | f31aa65 | this branch |
|---|---|---|---|---|
| ka_6 | ils | 13913.36 / 30913.4 / 0 / 17 | 13913.36 / 30913.4 / 0 / 17 | 30913.36 / 30913.4 / 0 / 0 |
| ka_6 | tabu | 20913.36 / 30913.4 / 0 / 10 | 12913.36 / 30913.4 / 0 / 18 | 30913.36 / 30913.4 / 0 / 0 |
| pg_6 | ils | 62923.96 / 67924.0 / 0 / 5 | 59923.96 / 67924.0 / 0 / 8 | 67923.96 / 67924.0 / 0 / 0 |
| pg_6 | tabu | 66923.96 / 67924.0 / 0 / 1 | 66923.96 / 67924.0 / 0 / 1 | 67923.96 / 67924.0 / 0 / 0 |

Trade-off: on capacity-limited horizons the plans now respect landing capacity instead of buying
volume with 1000-point overloads. `pg_18` (557762 m³ required, no plan completes it) delivers
421811–428391 m³ instead of 431023–432997 (v1.0.0) / 439577–440235 (f31aa65), i.e. 1–4 % less,
with 0 instead of ~600 overloads (objective +590k); in the Jaffray rolling smoke (`rolling_rerun_v101.py --smoke`,
28-day master, SA 50 iterations/window) the 14-day-window SA runs deliver 30380.5 m³ instead of
30913.4 m³ but with 0 instead of 35–37 landing overloads (full-horizon and 28-day windows still
deliver 30913.4 m³). The MILP's landing constraint is per day with a slack that is free at weight 0
— a pre-existing modelling difference left for the MILP owners (#115).

**2. Head-start waiver.** `SequencingTracker._upstream_exhausted` and the repair's
`meets_headstart` now add the upstream output staged in the current slot back before testing
"upstream finished", i.e. they use output before the slot, as the MILP `upstream_done` does.
`waiver_same_slot.py` now reports the day-3 skidder row as `missing_prereq` (the MILP rejects the
same plan as infeasible). Tests: `tests/sequencing/test_headstart_waiver.py` (2 of 4 fail on f31aa65).

**3. Missing `shift_id`.** `normalise_shift_ids` / `multi_shift_days`
(`evaluation/playback/adapters.py`): when any day has more than one shift slot
(`Problem.shifts`, i.e. shift calendar or timeline) and an active row (`assigned > 0`) has no
`shift_id`, playback, `compute_kpis`, stochastic playback and `fhops eval-playback` raise /
exit 1 with a clear message; single-shift scenarios keep the `S1` default. Internal callers: SA/ILS/
Tabu, the operational MILP driver and the HiGHS MIP driver always emit `shift_id`; rolling stitched
plans carry the solver's `shift_id`. Not changed here (other owners): `fhops evaluate` surfaces
the same `ValueError` as a traceback (only `eval-playback` is in this change's CLI scope), and
`planning.rolling.carry_forward_state` still replays a missing lock `shift_id` as `S1` in its own
replay (#117) — on multi-shift scenarios a day-level lock should expand to every shift or be
rejected, for consistency with playback.

**4. Duplicate DataFrame index.** Events work on `reset_index(drop=True)` copies and restore the
caller's index; `run_stochastic_playback` and `assignments_to_records` drop the index. `dupindex.py`
now gives identical delivered totals with/without duplicate labels (downtime 3728.035 / 3829.001 /
3876.63; weather 2844.927 / 1936.829 / 4148.061); f31aa65 gave 0.0 / 0.0 / 133.543 and
1104.866 / 1746.854 / 2143.296 with duplicates.

**5. Shift-hours fallback.** `playback.core.shift_hours_resolver(scenario)(machine, shift, day)`:
timeline definition, else `daily_hours / (#shift-calendar shifts of that machine that day)` (or the
day's shift count for a machine without entries, or the number of timeline shifts without a shift
calendar, else 1). Used for recorded `hours_worked`, shift availability (utilisation) and the
downtime fraction. `multishift.py`: shift calendar without timeline now records 8 h per shift
(24 h per machine-day, was 72 h) and a 4 h downtime removes 4/8 of a shift (was 4/24), identical to
the explicit 3 × 8 h timeline. Single-shift scenarios unchanged.

**6. Loss KPIs.** `downtime_production_loss_est` = Σ per downtime record of the proposed volume the
event removed (new private column `_downtime_lost` → record metadata `downtime_production_lost`;
fallback `rate × min(d / shift_hours, 1)`); `weather_production_loss_est` = Σ `_weather_lost`
(`volume × severity`; fallback `production × s / (1 − s)`); `weather_hours_est` = Σ
`severity × shift_hours`. On an unsequenced, uncapped scenario the downtime/weather loss equals the
drop in delivered volume exactly (tests). The f31aa65 formula (hours × delivered / all-role hours)
is replaced; shift/day summary schemas are unchanged.

**7. Landing-shock calibration.** Expected shocked landing-day fraction
`f = 1 − (1 − p)^D`. Defaults (`p = 0.1`, `D = 1`): 10 %. Synthetic presets were `medium` 0.18/2 →
32.8 %, `large` 0.25/3 → 57.8 %; now 0.025/2 → 4.94 % and 0.035/3 → 10.14 %. Documented in
`LandingShockConfig`, `LandingShockEvent`, `sampling_config_for`, `docs/howto/evaluation.rst`.
Shipped `examples/synthetic/*/metadata.yaml` keep the values used when they were generated (data
regeneration with the generator reproduces the CSVs; not needed, not edited).

**8. Deprecated fields.** `correlated_days` warns only for an explicit non-default value (`False`);
`seed_offset` (never used by any event) is deprecated the same way (non-zero warns, results
unchanged — verified). `sampling_config_dump` drops both from the synthetic preset merge and from
generated `metadata.yaml`. Loading the four shipped `examples/synthetic` metadata configs emits no
warning (test).

**9.** `eval-playback` help: the docstring and option help no longer use square brackets (Rich
dropped `[landing_multiplier_low, landing_multiplier_high]`); `[0, shift hours]` rephrased too.

**10.** `seed_offset`: see 8 (deprecated, documented in `SamplingEventConfig` and evaluation.rst).

Reference ladder (`fhops bench suite`, committed flags, into a temp dir): tiny7 SA ×3 / ILS / Tabu
and small21 SA ×3 / ILS / Tabu rows and assignment CSVs byte-identical. SoftwareX playback assets
(`run_playback_analysis.py --out-dir <tmp>`): every generated file byte-identical to
`docs/softwarex/assets/data/playback` (the two figure files are produced by a different script).

## Verification cadence (each child)
`ruff format --check src tests`, `ruff check src tests`, `mypy src`, `pytest`,
`sphinx-build -b html docs _build/html -W`, and `python scripts/check_formulation_assets.py`
when formulation sources change. Baseline at `v1.0.0`: 511 tests pass; ruff/mypy clean.

## Downstream
- Jaffray MASc Ch. 4 rolling-horizon grid is re-run on 1.0.1 with stitched-plan evaluation
  (`compute_rolling_kpis` vs full-horizon baseline); results decide how the manuscript
  characterises the companion study.
- The manuscript pins `fhops==1.0.1`, regenerates the playback figure and §3.2 values, updates the
  formulation (E6/E7 initial-state terms), and discloses the fix in the R2 response/cover letters.

## Cross-platform reproducibility note (2026-10-06)
Seeded SA results are bit-reproducible on a fixed platform (med42, 150 iters, seed 7 gives
-38434.22731600001 for PYTHONHASHSEED 0–7 locally; Python 3.12.3, numpy 2.5.3). Across platforms,
float summations differ in the last bits (CI: Python 3.11, numpy 2.4.6 → -38434.227316000004), and
on one CI run (6e60a36) such a difference flipped an SA acceptance decision (-38703.91). Regression
tests therefore compare floats to 1e-6 and assignments exactly; published benchmark values are
reproducible on the documented platform, not guaranteed bit-for-bit across numpy/Python builds.
