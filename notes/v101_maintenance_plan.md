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
   `RollingInfeasibleError`. (Superseded in §8.14: such locks are rejected up front.)
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
by #92); ILS "hybrid MIP warm start" calls `solve_mip` without an incumbent (resolved by #127, §8.19); `pyomo.contrib.solver`
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

### 8.15 Contract validation, packaging, CI, compatibility docs (#118)
Pre-release audit of the 1.0.1 candidate (f31aa65); evidence in `/tmp/opencode/audit-{1,2,4}-scratch/`,
`/tmp/opencode/floors118/`, `/tmp/opencode/compat118/`, `/tmp/opencode/roll118/`.

1. **Security / packaging.** The tree tracked an unrelated Django ("Codex") app state under
   `config/` (`secret_key`, `codex.sqlite3` with an admin password hash, `hypercorn.toml`,
   `cache/**`), shipped in the candidate sdist. Removed from the tree (`git rm -r config`; history
   not rewritten — the secret must be rotated), ignored (`/config/`, `*.sqlite3`, `secret_key`,
   `*.djcache`), excluded in `[tool.hatch.build]` (also `.env*`, `.pypirc`), and
   `release-build.yml` now fails if artifacts contain such files. The new sdist file list equals
   the candidate's minus the 26 `config/` files (wheel unchanged). Remaining non-secret leak noted:
   committed SoftwareX telemetry/benchmark assets contain absolute developer paths
   (`/home/gep/projects/fhops/...`), as in v1.0.0; left unchanged (regenerating assets is out of
   scope).
2. **Dependency floors** (fresh `uv` venvs, Python 3.11.17 and 3.12.3, every other dependency at
   its floor; smoke = import, `fhops --help`, tiny7 `solve-heur`, `solve-mip-operational` with and
   without `--incumbent` (HiGHS must accept the start), `eval-playback`, `plan rolling --solver mip`;
   full `pytest` at the floors):
   - `typer>=0.12.4`: 0.12.3 and older (incl. the old floor 0.9.0) fail to build the CLI
     (`RuntimeError: Type not yet supported: pathlib.Path | None`).
   - `pyomo>=6.9.2`: 6.9.1 cannot create `SolverFactory("highs")` (falls back to the ASL
     executable); ≤ 6.9.0 also fails the warm start (`LegacySolverInterface.solve()` rejects
     `warmstart`); 6.9.1 + highspy 1.7 lacks `HandleKeyboardInterrupt`. The audit's "6.9.4" floor
     came from testing 6.9.0 only; 6.9.2 and 6.9.3 pass everything.
   - `highspy>=1.8.1`: 1.7.0 was never published with files; 1.7.1–1.8.0 pass the smoke but report a
     rejected MIP start as "status unknown" (`tests/model/test_operational_driver.py::
     test_highs_warm_start_flags_infeasible_incumbent` fails).
   - `PyYAML>=6.0.1`: 6.0 has no Python 3.12 wheel and fails to build.
   - Unchanged floors verified working: click 8.1.0, rich 13.7.0, pydantic 2.6.0, pandas 2.2.0,
     numpy 1.26.0, pyarrow 15.0.0, optuna 3.5.0.
   - At the floors: `pytest` 448 passed / 212 skipped and the CLI suites 20 passed on both Pythons.
3. **Validation** (`Scenario._cross_validate`, `validate_initial_state`): locks outside the block's
   `[earliest_start, latest_finish]` window; locks on a block with `harvest_system_id` whose machine
   has no role or a role outside that system (registry = defaults overlaid with
   `harvest_systems`; unknown systems skip the check; blocks without a system accept any machine);
   `role_remaining > work_required + 1e-6`. Deviation: tolerance 1e-6 m³ (the tracker's
   `SEQUENCING_TOLERANCE`) instead of 1e-9, so carry-forward states built from HiGHS plans (~5e-7
   noise) cannot be rejected; measured on rolling SA/MILP runs (tiny7 7/4/2, 7/3/1; small21 21/7/3;
   med42 42/14/7; ka_6 28/14/7) the largest `role_remaining − work_required` in any window was
   −5.18 m³ (never positive). Role-less machines are rejected on explicit-system blocks because
   the operational MILP fixes their assignment to 0 there (the heuristics allow them), so such a
   lock was infeasible for the MILP. New checks run after all existing lock checks, so existing
   error messages are unchanged.
4. **Compatibility.** All 27 scenario YAMLs in the repo (examples, SoftwareX assets, test fixtures;
   2 intentionally invalid) and the 9 Jaffray scenarios load to identical `Scenario` dumps / identical
   errors under PyPI 1.0.0, the candidate (f31aa65), and this branch. 19 tiny7-derived edge cases
   document what each version accepts (`/tmp/opencode/compat118/cases.md`).
5. **CI.** `ci.yml` runs `tests/test_cli_operational_mip.py`, `tests/test_cli_playback.py`,
   `tests/test_cli_playback_exports.py` with `FHOPS_RUN_FULL_CLI_TESTS=1` (~10–30 s); `tests/cli/`
   already ran in the main pytest step; dataset CLI suites stay excluded (#103).
6. **Docs.** Removed "behaves exactly as in v1.0.0" claims (data contract, `ScenarioInitialState`,
   `Scenario.initial_state`, release notes); documented `Scenario.shift_labels()`, the
   `fhops>=1.0.1` requirement for `initial_state` / lock `shift_id` files, and every input now
   rejected at load (data contract "Compatibility with FHOPS 1.0.0", release notes). SoftwareX
   prose: introduction names v1.0.1 as the specific release; dependency row in
   `metadata/current_code_version.tex` updated to the new floors. Left for the manuscript authors:
   `illustrative_example.tex` ("FHOPS 1.0.0" in the benchmark software context) and
   `software_description.tex` (lists scipy, which is not a dependency).

### 8.12 Operational MILP robustness and correctness (#115)
Pre-release antagonistic audit of the 1.0.1 candidate (f31aa65); repro scripts in
`/tmp/opencode/audit-{1,2,4}-scratch/`, branch `issue-115-milp-robustness`. Design and decisions:

1. **Driver never raises for missing solutions** (`model/milp/driver.py`). Every solver path calls
   `solve(..., load_solutions=False)` and loads only when a solution exists (APPSI `load_vars()`;
   `model.solutions.load_from(results)` for Pyomo's `highs` `LegacySolverWrapper` and legacy
   plugins, the latter gated on optimal/feasible or limit + finite incumbent). The result gains
   `has_solution`, `outcome` (`optimal | feasible | infeasible | no_solution | error`),
   `solver_error` and `warnings`; without a solution `objective=None` and the assignment table is
   empty with the usual columns. Genuine solver failures are **not** reported as infeasible: HiGHS
   `ERROR` log lines (captured for the `highs` path via `tee=[stream]`, for APPSI via the private
   logger), solver exceptions (`ApplicationError`, `RuntimeError`), or an error/unknown
   termination without solution set `solver_error` (audit `opt3.py`: HiGHS refuses `threads=1`
   once its global scheduler was initialised with 36 threads — previously
   `NoFeasibleSolutionError`, i.e. "infeasible"). Exported production is clamped at 0 (no `-0.0`).
2. **Warm-start acceptance inference.** When the HiGHS log has no verdict, `accepted=True`,
   `acceptance="inferred"` if a solution was returned and either its `x` equal the seeded `x`, or
   the returned objective is ≥ the seed objective and the seed satisfies every constraint
   (checked lazily on the recorded seed values, tolerance 1e-6; the check costs ~10 s on ka_6, so it
   only runs when needed). `acceptance="log"` when the verdict comes from the log.
3. **CLI** (`solve-mip-operational` only): prints `outcome=…` and the objective only with a
   solution; an incumbent with no machine assignment ("objective = −Σ W") is reported as such
   instead of "No feasible assignment returned"; lock warnings and solver errors are printed; a
   solver error exits 1 (telemetry `status=error`).
4. **Locks never cause infeasibility.** `resolve_locked_slots(bundle)` (data.py, shared by the
   builder and the warm-start overlay) resolves locks per `(machine, slot)`: unavailable slots →
   pinned to 0 (silently, as before); contradictory locks (day outside the block window, role not
   in the block's system) → pinned to 0 with a warning; unknown ids / no matching slot / a second
   lock on a locked slot → ignored with a warning (scenario validation rejects these; #118). The
   activation coupling is reworked so `g` gates production only: `role_active_upper` excludes
   machines locked to the block in that slot, so a locked loader/head-start machine may be
   assigned and idle (`x=1`, `p=0`). For unlocked machines the published coupling
   (`Σx ≤ |M(r)| g`) is unchanged. Playback still flags a locked idle machine of a buffered role
   (`missing_prereq`; tracker semantics, #116).
5. **Per-upstream staged inventories (joins).** `inventory[u,b,s]` is indexed by the upstream role
   (`InventoryPairs` = `(u,b)` with ≥1 downstream role); balance
   `I_u = I_u^start + z_u − Σ_{r∈N(u)} z_r`, guard `Σ_{r∈N(u)} z_r ≤ I_u^start`, initial value
   `staged_inventory[u]`, head start `I_u(prev) ≥ B(g−h)` and loader threshold per upstream role.
   This is exactly the tracker (`role_inventory[(b,u)]` decremented by each downstream role's
   production; min over upstream; head start on the min slot-start volume), including roles feeding
   several roles (shared pool, consumption summed — keyed by `u`, not by `u→r` pairs, which would
   double-count a fork against the tracker; identical without forks). For linear chains the model
   is the previous one with the inventory renamed from the downstream to the upstream role: LP files
   written with numeric labels are **byte-identical** to f31aa65 for 30 random loader-free chains
   (head starts, consistent initial states).
6. **Dynamic loader threshold.** `I_u(prev) ≥ min(q_b, W_b − D_b(prev(s)))·g` (tracker rule:
   `min(loader_batch, remaining_work)`; the tracker's within-slot remaining is never larger, so the
   MILP is never less strict). Exact linearisation: slots where the remaining volume provably exceeds
   a truckload (`D̄_b(<s) ≤ W−q`, terminal fleet capacity bound) keep `I ≥ q·g`; blocks with
   `W ≤ q` use `I + D ≥ W·g`; tail slots use a monotone block binary `λ_{b,s}`
   (`I ≥ q(g−λ)`, `I + D ≥ q g + (W−q)λ`, `D ≥ (W−q)λ`, `λ_s ≥ λ_prev`); big-Ms are `W` and `q`.
   `D` uses `role_cumulative` of the terminal roles. Loader head starts and the truckload rule are
   now separate constraints (the waiver applies to the head start only, as in the tracker).
7. **`role_remaining > work_required`.** Cap `Σ z ≤ min(R⁰, W)`; the head-start waiver still
   compares with the carried-in `R⁰` (the tracker's `role_remaining`), so it never fires when
   `R⁰ > W`. Where the flow balances do not imply it — systems with forks / several terminal roles,
   or chains/joins whose carried-in state violates `R_r + Σ_{path} staged ≤ W` — the per-slot cap
   `z_r(s) + D_b(≤s) ≤ W_b` mirrors the tracker's cap of every assignment at the remaining volume
   (without it 1/100 fork+state fuzz cases replayed with a violation).
8. **Blackouts on partial shift calendars.** `build_blackout_slots` blocks, on every blackout day,
   every grid slot of the day (`pb.shifts`) plus each machine's own calendar shifts; fallback to
   timeline names / `S1` only for days without grid slots. API unchanged; slot sets are unchanged
   when every machine has calendar entries on the grid or no shift calendar exists.
9. **Formulation** (`fhops_operational_formulation.md`, TeX/RST regenerated with pandoc 3.6, which
   reproduced the committed files byte-for-byte before editing): sets `P^stg`, `N_{u,b}`, `P^thr`,
   `P^act`, `P^cap`, `S^tail_b`; `B_{r,b}` fallback (own capacity when no upstream machine has a
   rate) and `Q_{r,b}` definition; `R⁰`/`R = min(R⁰, W)`; variables `I_{u,b,s}`, `λ`, notation
   `D_{b,s}`; E7/E8 rewritten; per-slot cap; locks with `χ_k`; fleet-wide blackouts; "Changes from
   FHOPS v1.0.0 (1.0.1)" rewritten as one list (i)–(vii).

Evidence (before = f31aa65 copy, after = branch; full tables in CHANGE_LOG #115): every audit
repro is fixed (locks feasible, joins replay with 0 violations, loader tail 80/98 → 100,
`fuzz_incons` 7/40 → 0/40, `opt3.py` reported as solver error, blackout day empty); random DAG
MILP→playback replay (`/tmp/opencode/t115/fuzz_dag.py`, 100 seeds each): joins 33 → 0, forks
35 → 0, joins + random initial state 44 → 0, forks + state 36 → 0 bad cases (planned terminal
production == playback delivered in every clean case). Reference: tiny7 optimal 4388.082752
unchanged; 60 random linear pipelines with loaders give identical optimal objectives; at equal time
limits (both versions side by side) small21 improves (120 s: empty → −13655.25; 600 s: 15004.45 →
15645.73) and med42 (120/600 s) / ka_6 (120 s) stay at the empty incumbent for both. Model size:
ka_6 +1967 binaries (+2.3 %, loader tail), +7911 constraints (+2.9 %); tiny7 +12 binaries; build
time unchanged within noise.

The tiny7 MILP has alternative optima (a no-good cut on the returned assignment re-solves to the
same objective), so the regression tests check objective, constraint feasibility and replay
consistency instead of exact assignments.

Hand-offs: playback flags a locked idle machine of a buffered role (`missing_prereq`) — tracker
semantics owned by #116; the rolling MILP hook may forward `solver_error`/`warnings` (#117);
contradictory locks are validated at scenario level by #118; the legacy day-level `solve_mip`
(`fhops solve-mip`) still raises on infeasible models (its CLI formats the objective as a float).

### 8.14 Rolling-horizon robustness (#117, audit)
Pre-release audit of the 1.0.1 candidate (f31aa65; repros in `/tmp/opencode/audit-1-scratch/`).
Branch `issue-117-rolling-robustness`.

Findings → fixes:
1. **MILP windows without a solution crashed the run** (`lockinfeas.py` MILP 2/2:
   `NoFeasibleSolutionError` from Pyomo). Policy now: `MILPSolver` returns
   `SolverOutput(has_solution=False)` when the driver raises or reports no solution
   (`has_solution` false / `objective is None`, so it works before and after #115's driver change);
   `run_rolling_horizon` records `status="no_solution"`, `objective=None`, a warning (iteration,
   run, `UserWarning`), locks **nothing** for the lock span (machines idle; user locks there are not
   applied and are counted in the warning), so the carried state is unchanged across the span, and
   continues. `fail_on_empty_window=True` / `--fail-on-empty-window` raises
   `RollingInfeasibleError` (naming the iteration; `iteration_index`, `partial_result`). Windows with
   nothing to plan (no blocks, no rates, no available shift slots) are `status="skipped"` and the
   solver is not called (before: `RollingInfeasibleError` for "no blocks"/"no production rates").
2. **Empty windows were silent** (ka_6 smoke: 30 s MILP windows return an all-zero incumbent with
   objective = −leftover penalty). New per-iteration `planned_delivered` (window plan replayed on the
   window scenario), `locked_delivered`, `empty` (window blocks hold work but 0 locks or 0 planned
   delivery), and run counts `empty_windows` / `no_solution_windows` / `skipped_windows` (+ index
   lists) in `summarize_plan`, `RollingPlanResult.empty_windows` / `no_solution_windows`, and
   `evaluate_rolling_plan` metadata.
3. **Locks outside their block window** behaved differently per window setting (`lockout.py`: SA 6/6
   silently dropped the lock, MILP 6/6 infeasible, 3/3 `... does not overlap`). Now rejected up front
   for every lock, before any solve, with one message (also rejected at validation once #118 lands).
   Valid locks always lie in a window that keeps their block, so the slicer's overlap error is
   unreachable from `run_rolling_horizon`. Downstream user locks made infeasible by short
   non-overlapping windows go through policy 1 (documented limitation).
4. **Partial `shift_calendar`** (`shiftcal.py`): a window with no calendar entries fell back to `S1`
   (rolling 4/4 delivered 2400 m³ vs 1600 m³ direct). The slicer now emits explicit `available=0`
   entries for such windows (no shift slots), and the window is skipped: 1600 m³.
5. **Tests**: the v1.0.0 zero constant in `test_stitched_kpis_bounded_and_close_to_full_horizon` is
   replaced by: full horizon finishes tiny7; for 7/4/2 and 7/6/3, 0 violations, no empty windows,
   Σ `locked_delivered` = stitched delivery, SA ≥ 95 % of full, MILP delivery = planned loader
   production and ≥ 99 % of full for `sub=6`. `_assert_window_matches_replay` sorts by the
   scenario's slot order (night-before-day test added). `tests/planning/test_rolling_robustness.py`
   adds a hand-written linear-chain state machine (no `assignments_to_records`) compared with
   carried state, window scenarios, iteration telemetry and stitched KPIs (2/3 roles, 1/2 shifts,
   user initial state; SA and MILP), plus tests for 1–4; CLI partial-output tests.
6. Small hardening: carried `role_remaining` is capped at the block's remaining terminal volume
   (float noise must not violate #118's `role_remaining <= work_required`); day-level locks get the
   day's only shift label before playback/exports (playback will reject unlabeled multi-shift rows
   after #116; multi-shift days keep `None`).

Evidence: audit harness `run_adv.py` (5 scenario variants × SA/MILP × 5 window settings): 50 runs,
0 state problems, 0 sequencing violations. Jaffray smoke (`--smoke`, ka_6): 10/10 runs ok, SA
30913.4 m³ in every run, MILP 30 s windows return all-zero incumbents → flagged `empty` (baseline 1,
14/14 2, 28/14 2, 14/7 3, 28/7 3 empty windows), 0 violations.

### 8.16 SoftwareX benchmark asset consistency (#119, audit)
Pre-release audit finding (audit-3 MINOR 9): committed med42 SA assignment CSVs did not match
`summary.csv`. Branch `issue-119-softwarex-asset-consistency`; scratch in `/tmp/opencode/w119/`.

**Audit tool.** `docs/softwarex/manuscript/scripts/audit_asset_consistency.py` (no solver runs):
every benchmark/scaling `summary.csv` row vs its assignment CSV (`compute_kpis`: assignments,
delivered production, mobilisation, completed blocks, day utilisation), `data/tables/*` vs a fresh
`build_tables.py` rendering (optionally vs the manuscript's `sections/includes/*.tex`), each
deterministic playback export re-played from the benchmark CSV it claims to use (day-level
production/hours/mobilisation) plus `metrics.json` vs the benchmark KPIs, `scaling_summary.csv` vs
the tier summaries, and the tuning comparison/report vs `runs.jsonl` (best/mean objective, mean
runtime). Also checked separately: every `summary.json` equals its `summary.csv` (rows matched on
solver/preset).

**Re-runs** (`fhops bench suite` on this branch, committed `generate_assets.sh` settings, into
`/tmp/opencode/w119/regen`; med42 split into SA / ILS / Tabu processes, the same per-solver calls
and arguments): every row compared column by column with the committed `summary.csv` except
`scenario_path`, `runtime_s` and the run-dependent `best_heuristic_*`/ratio columns, and every
assignment CSV compared byte for byte.

Consistency matrix (KPI = assignments, delivered m³, mobilisation, completed blocks, day
utilisation re-derived from the CSV; "re-run" = deterministic re-run reproduces the committed row
exactly and the CSV byte for byte):

| Scenario | Solver / preset | KPI vs CSV (before) | Re-run | Table row | Action |
|---|---|---|---|---|---|
| tiny7 | SA default / diversify / mobilisation | OK | reproduced, CSV identical | OK | none |
| tiny7 | ILS, Tabu | OK | reproduced, CSV identical | OK | none |
| small21 | SA default / diversify / mobilisation | OK | reproduced, CSV identical | OK | none |
| small21 | ILS, Tabu | OK | reproduced, CSV identical | OK | none |
| med42 | SA default | **stale** (mobilisation 10662.04 vs 10564.68) | reproduced (−27271.221414, 32071.863994 m³, 10564.68) | **stale** (−28271.22 / 124.48 s / 10662.04) | CSV replaced by re-run output; table regenerated |
| med42 | SA diversify | **stale** (214 vs 210 rows, 32715.39 vs 32297.03 m³, 8 vs 6 blocks) | reproduced (−30977.725738) | not tabled | CSV replaced by re-run output |
| med42 | SA mobilisation | OK | reproduced, CSV identical | not tabled | none |
| med42 | ILS | OK | reproduced, CSV identical | **stale** (−41581.70 / 182.33 s / 32702.07 / 10662.28) | table regenerated |
| med42 | Tabu | OK | reproduced, CSV identical | **stale** runtime (177.37 s vs 7391.10 s) | table regenerated |
| synthetic_small | SA ×3, ILS, Tabu | OK | reproduced, CSV identical | OK | none |
| scaling small/medium/large | SA | OK; `scaling_summary.csv` = tier summaries | reproduced (objective, assignments, CSV identical) | n/a | none (see manuscript note) |
| tuning (4 scenarios × 5 tuners) | — | comparison/report = `runs.jsonl` | not re-run | med42 row **wrong** (sense) | `build_tables.py` fixed, table regenerated |
| playback deterministic (6) | — | day.csv = replay of the benchmark CSV, except med42 SA (stale CSV) | — | — | med42 SA re-derived; `metrics.json` schema fixed |

Provenance of the stale files (from the committed `telemetry.jsonl`): on 2025-12-03 a reduced
med42 run (SA 2000 iterations: default −28271.22, diversify −41420.41; ILS 400: −41581.70; Tabu
1000: −46063.73, all from `examples/med42/scenario.yaml`) overwrote `sa_assignments.csv`,
`sa_assignments_diversify.csv` and the tables, while the full-budget rows were merged back into
`summary.csv`. The regenerated SA CSVs are byte-identical to the copies in the manuscript
repository's import snapshot (`fhops-manuscript` 510b7f5, `assets/data/benchmarks/med42`), i.e. the
full-budget files existed but were never committed here.

Decisions:
1. **Summaries are not rewritten.** Every committed row was reproduced, so `summary.csv/json` and
   `telemetry.jsonl` are kept byte-for-byte; only the two stale CSVs are replaced with the files
   written by the reproducing run. Published runtimes therefore stay the committed ones: the
   tables take `runtime_s` from `summary.csv`, which is unchanged (re-run wall-clock times on the
   loaded 72-core host differed by −49 % … +59 % and are recorded only in the scratch logs).
2. **`build_tables.py` med42 sense** `minimize` → `maximize` (all FHOPS heuristics maximise; the
   manuscript R1 change log describes this fix, but it never reached this repo). Table 4 is
   unaffected (one row per solver); Table 5 med42 becomes Bayes −35485.30, Δ −8214.08, 5.29 s. The
   regenerated `.tex` tables equal the manuscript's `sections/includes/*.tex` byte for byte.
3. **Playback `metrics.json`** (written by `run_playback_analysis.py`): `total_production` is now
   the terminal delivered volume (tracker `delivered_total`, = benchmark `kpi_total_production`),
   with `total_production_std`, `remaining_work`, and `all_roles_production_units` (the former
   value: production summed over every role, e.g. tiny7 17658.81 vs 4414.70 m³ delivered). Hours
   and mobilisation are per-sample means (they were summed over the 50 stochastic samples, e.g.
   med42 SA mobilisation 533102 = 50 × 10662.04). Delivered volumes come from an in-process replay
   with the `eval-playback` defaults + `STOCHASTIC_OPTIONS`; the script aborts unless the replay's
   day-level production and hours equal the CLI's `day.csv`. `summary.md` still prints the CLI's
   all-roles "Total production units" (CLI exporter, unchanged).
4. **med42 SA playback** re-derived from the corrected CSV: production/mobilisation columns change
   (mobilisation 10662.04 → 10564.68; stochastic mean delivered 28195.59 m³), utilisation is
   unchanged (same machine-shifts worked: 0.558201 deterministic, 0.553755 stochastic), and the
   figure (`utilisation_robustness.png/pdf`) is byte-identical.
5. **small21 provenance.** `generate_assets.sh` never generated the committed small21 assets; it
   now has a small21 case with the verified settings (SA 4000, ILS 800, Tabu 7000, batch 1,
   4 workers).

Findings left open (reported, not changed here):
- **Scaling runtimes quoted in the manuscript are not these assets.** FHOPS assets (reproduced
  here except wall-clock) give 31.68 / 83.58 / 105.42 s; the manuscript quotes 31.81 / 84.88 /
  108.97 s and embeds a `runtime_vs_blocks.png` from the manuscript repository's own asset snapshot
  (510b7f5, same objectives and assignment counts, different run). The authors must either quote
  the FHOPS values and figure or treat the snapshot as the source of record.
- **Heuristic objective ≠ fresh evaluation of the exported schedule** (pre-existing; identical at
  v1.0.0). SA/ILS/Tabu report the score of their internal best `Schedule`, whose per-machine
  mobilisation cache can lack machines: candidates reach `evaluate_schedule` with an empty
  `mobilisation_cache` and a `dirty_machines` set holding only the mutated machines, so
  `_ensure_mobilisation_stats` charges only those machines. Re-scoring the exported CSVs gives
  lower objectives (gap: tiny7 10.748 for every row; small21 54–151; med42 SA 3060.62 / 837.70 /
  3088.80, ILS 2031.90, Tabu 0; synthetic 0). Delivered production and mobilisation in the tables
  come from `compute_kpis` and are correct; the Objective column and the tuning objectives are the
  solvers' internal scores. A fix changes search trajectories, so every benchmark/tuning asset
  would have to be regenerated (src owners; not 1.0.1 asset work).
- The in-repo manuscript draft (`docs/softwarex/manuscript/sections/illustrative_example.tex`)
  still quotes the stale med42 values (ILS −41581.7 in 182 s, SA −28271.2 in 124 s, Tabu 177 s,
  Random −39725.9); the submitted manuscript (separate repo) already has the corrected values.
- Under 1.0.1 `synth generate` writes different sampling metadata (`metadata.yaml`: deprecated
  keys dropped, medium/large landing-shock presets, #116); scenario CSVs, benchmark rows and
  assignments are unchanged, so the committed dataset metadata was left as generated.

Manuscript-quoted values (old → new): Table 4 med42 SA −27271.22 / 1245.04 s, ILS −33452.28 /
1791.73 s, Tabu −46063.73 / 7391.10 s, production 30026.28–33025.19 m³, mobilisation
9846.12–10682.68 CAD — unchanged; Table 5 Bayes −35485.30, Δ −8214.08, 5.29 s — unchanged (the
FHOPS table now matches); §3.2 utilisation tiny7 0.37 → 0.36, med42 SA 0.558 → 0.554, ILS 0.564 →
0.559, synthetic-small 0.62 → 0.60 — unchanged; scaling 31.81 / 84.88 / 108.97 s — **not backed by
the FHOPS assets** (31.68 / 83.58 / 105.42 s).

### 8.17 Legacy solve-mip no-raise, rolling hook warnings, manuscript copy (#124)
Hand-offs from #115 (§8.12) and #118 (§8.15). Branch `issue-124-legacy-mip-hook-warnings`; repro
scripts in `/tmp/opencode/t124/`.

1. **Legacy driver** (`optimization/mip/highs_driver.py`, `solve_mip`): same policy as §8.12.
   APPSI interfaces (HiGHS, Gurobi) run with `config.load_solution = False` and load with
   `load_vars()` only when `best_feasible_objective` is set; Pyomo's `highs` interface and the
   `gurobi` plugin go through the operational driver's `_run_solver` (`load_solutions=False`).
   The HiGHS log is captured (private logger for APPSI; `tee=[stream]` for `highs`), and the
   operational driver's classification is reused (imported lazily: `fhops.model.milp.driver`
   imports `fhops.evaluation.sequencing`, which imports `fhops.optimization`). Result keys added:
   `has_solution`, `outcome`, `solver_status`, `termination_condition`, `solver_error`,
   `warnings`; `objective=None` and an empty assignment table (usual columns) without a solution.
   `SolverUnavailable` only for a missing solver; unknown drivers raise `ValueError` before the
   model is built. Gurobi: an APPSI failure falls through to the `gurobi` plugin (noted in
   `warnings`); under `driver="auto"` a failed Gurobi run falls back to HiGHS (noted in `warnings`;
   1.0.0 did the same for exceptions). Normal solves are unchanged: 20/20 cases (regression fixture
   and 9 linear chains × `auto`/`highs-exec`) give identical objectives and assignment tables
   before (b73376d) and after.
2. **CLI.** `solve-mip` prints `MIP outcome=… solver_status=… termination=… objective=…|n/a`,
   solver errors and warnings; without a solution it writes the empty table and skips the KPI
   summary. Exit codes: 0 solver ran (incl. infeasible / no incumbent), 1 solver error or solver
   unavailable, 2 bad arguments (unknown `--driver` → `BadParameter`). `benchmark` prints
   `MIP obj=n/a (outcome=…)`, skips MIP metrics, still runs SA, exits 1 after SA on a MIP solver
   error. Only these two functions in `cli/main.py` changed (#116 edits `eval-playback`); the
   `SolverUnavailable` import is local to them.
3. **Finding (pre-existing, not fixed): the legacy MIP is infeasible for every bundled example.**
   `system_loader_buffer` (`constraints/system_sequencing.py`) is
   `Σ_{≤s} prod_loader ≤ Σ_{<s} prod_prereq − batch`; in the first shift the right side is
   `−batch` (30 m³), so any block whose system has a loader role with machines makes the model
   infeasible. tiny7, small21 and med42 are proven infeasible by HiGHS (also at `v1.0.0`, where
   `solve-mip` raised `RuntimeError`); large84 has 48 such rows (model build > 15 min, not
   solved). The regression fixture (no loader) solves (objective 8.0). The quickstart now uses
   `solve-mip-operational` for tiny7, and the CLI reference / API page document the limitation.
   Still showing `solve-mip` on examples (left for a docs/formulation follow-up, outside this
   issue's files): README quickstart (tiny7), `docs/howto/thesis_eval.rst`,
   `docs/howto/mobilisation_geo.rst`, `docs/howto/system_sequencing.rst` (med42),
   `docs/api/fhops.evaluation.rst` (tiny7 example). Fixing the constraint (`− batch · active`)
   changes the legacy model and is not in scope for 1.0.1. (Resolved by retirement in #127, §8.19.)
4. **Rolling hook** (`MILPSolver`): appends `solver_error=<text>` and each driver `warnings` entry
   to `SolverOutput.warnings` after the status lines, skipping duplicates;
   `run_rolling_horizon` already copies them into the iteration warnings. Real driver warning
   that #118 validation still allows: a block whose `harvest_system_id` is not in the registry
   (scenario without custom `harvest_systems`) skips the validation role check, while the MILP knows
   no roles for that system and pins the lock to 0 with a warning (the block cannot be harvested
   by the MILP at all; noted, not changed). Tests: fake driver (with/without solution, duplicates)
   and this real HiGHS case.
5. **Manuscript copy** (`docs/softwarex/manuscript/sections/`): `illustrative_example.tex` states
   that the benchmarks were generated with FHOPS 1.0.0, reproduce exactly under 1.0.1 on the
   documented platform, and that the playback assets were regenerated with 1.0.1 (§8.5).
   `software_description.tex`: scipy removed (not a dependency, not imported); dependency lists
   now match `pyproject.toml` (highspy, Click, PyYAML for scenario files, pyarrow for Parquet).

### 8.19 Retire the legacy MIP builder; ILS hybrid warm start (#127, #104)
Follow-up to the §8.17 finding (legacy MIP infeasible for every scenario with a loader role).
Branch `issue-127-legacy-mip-retirement`; scratch in `/tmp/opencode/t127/`.

1. **Delegation** (`optimization/mip/highs_driver.py`). New `solve_with_operational_milp(pb,
   time_limit, driver, debug)` builds the operational problem and calls
   `solve_operational_milp(bundle, solver, time_limit, tee=debug, context=ctx)`; legacy driver
   names map via `operational_solver_for_driver`: `auto` → `("gurobi", "highs")` (only available
   solvers; a Gurobi `solver_error` is retried with HiGHS and noted in `warnings`, as in 1.0.0/#124),
   HiGHS drivers → `highs`, `gurobi`/`gurobi-appsi`/`gurobi-direct` → `gurobi`/`appsi_gurobi`/
   `gurobi_direct`. Unknown driver → `ValueError`; no available candidate → `SolverUnavailable`.
   Result = operational result (#124 keys + `production`, `warm_start`) + `solver`.
   `solve_mip` warns (`LegacyMipDeprecationWarning`, a `DeprecationWarning`, `stacklevel=2`, new
   module `optimization/mip/deprecation.py`) and delegates. `build_model` warns; the #124 legacy
   solve path is kept as private `_solve_legacy_mip` (suppresses the builder warning) so the
   infeasibility finding stays reproducible (`tests/test_legacy_mip_driver.py`). DeprecationWarning
   rather than FutureWarning: shown for calls from scripts/notebooks and under pytest, hidden when
   triggered inside the CLI, which prints its own one-line notice.
2. **CLI.** `solve-mip`: one `Deprecated: …` line, then the #124 output and exit codes (0/1/2)
   unchanged; an incumbent without machine assignments skips the KPI summary (as in
   `solve-mip-operational`). `benchmark`: MIP step via `solve_with_operational_milp` (no notice).
   Only these two functions in `cli/main.py` changed. `bench suite --driver auto --include-mip`:
   since #115 an unavailable Gurobi is a `solver_error` instead of an exception, so the candidate
   loop never fell back and the MIP row was empty (tiny7: objective NaN, 0 assignments); the loop
   now continues on `solver_error` while candidates remain (`cli/benchmarks.py`).
   `scripts/ingest_mip_baselines.py` uses `solve_with_operational_milp` and skips runs without a
   solution (it crashed on `objective=None` since #124).
3. **ILS hybrid** (`heuristics/ils.py`): at each stall the operational MILP (HiGHS,
   `hybrid_mip_time_limit`) is solved on the ILS run's own bundle (same objective-weight overrides)
   with `incumbent_assignments` = best ILS schedule (APPSI HiGHS MIP start, #99). The MILP schedule
   (rows with `assigned=1`) is re-scored by the heuristic evaluator and adopted only if better; no
   solution → ILS schedule kept. `meta["hybrid_mip"]` (only when enabled) records each solve. tiny7
   (iters 3, seed 1, stall 1): seeded 23 slots, HiGHS log "MIP start solution is feasible",
   MILP 4402.80 (ILS weight overrides) ≥ seed MILP objective; heuristic score 4306.52 → 4360.01
   (adopted). Before: legacy MIP infeasible → exception swallowed → no-op.
4. **Reference ladder unchanged.** Committed SoftwareX benchmark/tuning telemetry has
   `hybrid_use_mip: false` everywhere (`generate_assets.sh` never passes `--ils-hybrid-use-mip`;
   `run_tuner.py` uses the `short` tier; only `run_tuning_benchmarks.py`'s `long` tier enables the
   hybrid). Re-runs with committed flags: tiny7 SA×3/ILS/Tabu and small21 ILS/Tabu summary rows
   identical in every non-runtime column (raw CSV text) and all 7 assignment CSVs byte-identical.
5. **Docs** (README, quickstart, thesis_eval, mobilisation_geo, system_sequencing MIP example,
   ils, benchmarks, data_contract note, CLI reference, API pages, release notes): examples use
   `solve-mip-operational`; `solve-mip` documented as deprecated alias with the option mapping.
   med42 MILP examples moved to tiny7 (HiGHS 600 s on med42 ends at the empty incumbent,
   objective −38193.23); the regression-fixture MIP line dropped (its `ground_sequence` system is not
   in the registry, so the operational MILP cannot harvest it). Every command on the touched pages
   ran in a temp copy (results in CHANGE_LOG); pre-existing, not changed here:
   `system_sequencing.rst` `fhops solve-ils … --include-mip False` (no such option, exit 2) and its
   default-scenario `bench suite` (hours; not run) — that page's non-MIP parts belong to #125.
### 8.18 Solver consistency: landing capacity, day locks, idle locked slots, `fhops evaluate` (#125)
Hand-offs from #116 (§8.13 items 1 and 3) and #115 (§8.12 hand-offs). Branch
`issue-125-landing-locks-alignment`; scripts in `/tmp/opencode/w125/`.

1. **Landing capacity (E11).** Heuristics (v1.0.0 behaviour, unchanged): per `(day, shift)` slot,
   every machine assigned to a block of landing `ℓ` counts; at `landing_surplus = 0` each machine
   beyond `daily_capacity` costs 1000 (the assignment's landing slot is still counted); otherwise
   `landing_surplus_total` grows by `used − C` for each machine beyond capacity, i.e. the `k`-th
   machine beyond capacity adds `k` (`e` surplus machines → `e(e+1)/2`). The MILP counted
   machine-shifts per **day** (`Σ_σ x ≤ C + S_{ℓ,d}`) and `S` was free at weight 0, so landings never
   bound. Now `landing_capacity[ℓ, d, s]`: `Σ_{b∈ℓ} Σ_m x_{m,b,s} ≤ C_ℓ` at weight 0 (no slack
   variable), else `≤ C_ℓ + Σ_{k=1}^{|M|−C_ℓ} S_{ℓ,s,k}` with `S ∈ [0, 1]` and objective
   `−ω Σ k·S_{ℓ,s,k}` (increasing marginal price ⇒ the LP fills pieces in order, exactly the
   heuristics' triangular accounting; a single linear slack would have priced `e` instead of
   `e(e+1)/2`, so soft-mode objectives of the same plan would differ between SA and MILP). The
   legacy day-level `solve-mip` builder (other owner, #124) already uses a per-slot linear slack.
   - **Locks.** With a hard capacity, locks alone can exceed it (scenario validation does not reject
     this; with a soft weight it is a priced choice). Decision: that slot's limit becomes the number
     of machines locked to the landing (`_landing_slot_capacities`, effective locks only, i.e.
     after `resolve_locked_slots`), so the locks hold, no other machine may join, and a warning is
     returned in `result["warnings"]`. The heuristics charge the same unavoidable overload (1000 per
     locked machine beyond capacity), so both solvers still agree. Rejected: pinning surplus locked
     machines to idle (silently breaks user locks) and making the model infeasible (contradicts
     §8.12 item 4).
   - Warm start: `landing_usage` is per slot; the pieces `1..(usage − C)` are seeded with 1. A
     heuristic incumbent that overloads a landing (single-shift repair is not landing-aware) is now
     infeasible and rejected (`med42` greedy, `--iters 0`, 60 s: rejected; accepted at 86cd4d9 with
     objective 22812.11). Documented in `docs/howto/mip_warm_starts.rst`.
   - Docs: formulation (`C_ℓ`, `K_ℓ`, `S_{ℓ,s,k}`, objective, constraint with `N^lock`, domain,
     change (viii), mapping; TeX/RST regenerated with pandoc 3.6, which reproduced the committed
     files byte-for-byte first), `Landing.daily_capacity` / `ObjectiveWeights.landing_surplus`
     docstrings, `system_sequencing.rst`, `data_contract.rst`, release notes.
2. **Day-level locks.** MILP (`resolve_locked_slots`): a lock without `shift_id` pins every grid
   slot of its day where the machine is available. Heuristics: `lock_for` returns the day lock for
   every slot, the repair clears unavailable slots — same plan (new tests: SA and MILP rolling, and
   a direct SA solve with one unavailable shift, place the machine in exactly the available shifts).
   Rolling: `_fill_shift_ids` (label only single-slot days, keep `None` otherwise → playback
   rejected the rows on multi-shift scenarios since #116, and `S1` before) is replaced by
   `_expand_day_locks`: one shift lock per available slot (grid order; slots already covered by a
   shift lock of the machine are skipped; no available slot → dropped, the MILP pins it idle). A day
   lock with a planned `production` covering > 1 slot raises `ValueError` (split ambiguous).
   Applied in `carry_forward_state` (replay and `last_block_id` order), `_run_iteration` (hook
   output, so `RollingPlanResult.locked_assignments` is always shift-level),
   `rolling_assignments_dataframe(..., scenario=...)` (new optional keyword for hand-built results)
   and `compute_rolling_kpis` (results and `ScheduleLock` sequences; DataFrames are passed to
   playback as given). Single-slot days: the label is filled as before, but a day lock on an
   unavailable single slot is now dropped (previously replayed; MILP semantics).
3. **Idle locked slots.** `SequencingTracker.process`: a proposal `≤ SEQUENCING_TOLERANCE` is an idle
   slot; head-start and truckload checks are skipped (they bind a producing role, the MILP's
   `role_active`); role violations still apply. Heuristics always propose the machine's rate
   (> 0), so they are unaffected; playback of rate-based rows is unchanged. The strict xfail on
   `test_downstream_user_lock_in_short_windows_does_not_crash[2-2]` is removed; the test now also
   asserts that the MILP idles the locked skidder (`production == 0`). A producing row without
   staged input is still flagged (`tests/sequencing/test_idle_locked_slot.py`).
4. **`fhops evaluate`** catches `ValueError` from `compute_kpis` (missing `shift_id` and other input
   errors) → red message, exit 1 (test parametrised with `eval-playback`).

Evidence (`milp_cmp.py`: HiGHS, scenario weights, both versions side by side at equal time limits;
"landing penalties" = `evaluate_schedule` without its repair pass on the MILP plan, penalty minus
the penalty with unbounded landing capacity, /1000; the remaining heuristic penalties are
sequencing violations from the heuristics' rate-based proposals, not landing):

| Scenario (time limit) | Version | Outcome | Objective | Rows | Playback delivered m³ | Playback violations | Landing overloads (per slot) | Heuristic landing penalties |
|---|---|---|---|---|---|---|---|---|
| tiny7 (60 s) | 86cd4d9 | optimal | 4388.08 | 24 | 4414.70 | 0 | 12 | 12 |
| tiny7 (60 s) | #125 | optimal | 279.80 | 14 | 2360.56 | 0 | 0 | 0 |
| small21 (120 s) | 86cd4d9 | feasible | -13655.25 | 148 | 1987.56 | 0 | 72 | 72 |
| small21 (120 s) | #125 | feasible | 2610.62 | 54 | 9288.79 | 0 | 0 | 0 |
| small21 (600 s) | 86cd4d9 | feasible | 15645.73 | 118 | 15966.97 | 0 | 49 | 49 |
| small21 (600 s) | #125 | feasible | 11433.31 | 87 | 13940.62 | 0 | 0 | 0 |
| med42 (120 s) | 86cd4d9 | feasible (empty incumbent) | -38193.23 | 0 | 0 | – | – | – |
| med42 (120 s) | #125 | feasible (empty incumbent) | -38193.23 | 0 | 0 | – | – | – |
| med42 (600 s) | 86cd4d9 | feasible (empty incumbent) | -38193.23 | 0 | 0 | – | – | – |
| med42 (600 s) | #125 | feasible (empty incumbent) | -38193.23 | 0 | 0 | – | – | – |
| ka_6 (120 s) | 86cd4d9 | feasible (empty incumbent) | -30913.36 | 0 | 0 | – | – | – |
| ka_6 (120 s) | #125 | feasible (empty incumbent) | -30913.36 | 0 | 0 | – | – | – |
| ka_6 (600 s) | 86cd4d9 | feasible | 23353.58 | 272 | 27133.47 | 0 | 12 | 12 |
| ka_6 (600 s) | #125 | feasible (empty incumbent) | -30913.36 | 0 | 0 | – | – | – |
| ka_6 (1800 s) | 86cd4d9 | optimal | 30913.36 | 473 | 30913.36 | 0 | 27 | 27 |
| ka_6 (1800 s) | #125 | feasible (empty incumbent) | -30913.36 | 0 | 0 | – | – | – |
| ka_6 (600 s, SA seed) | 86cd4d9 | optimal | 30913.36 | 277 | 30913.36 | 0 | 0 | 0 |
| ka_6 (600 s, SA seed) | #125 | optimal | 30913.36 | 277 | 30913.36 | 0 | 0 | 0 |
| pg_6 (120 s) | 86cd4d9 | feasible (empty incumbent) | -67923.96 | 0 | 0 | – | – | – |
| pg_6 (120 s) | #125 | feasible (empty incumbent) | -67923.96 | 0 | 0 | – | – | – |
| pg_6 (600 s) | 86cd4d9 | feasible (empty incumbent) | -67923.96 | 0 | 0 | – | – | – |
| pg_6 (600 s) | #125 | feasible (empty incumbent) | -67923.96 | 0 | 0 | – | – | – |
| pg_6 (1800 s) | 86cd4d9 | feasible (empty incumbent) | -67923.96 | 0 | 0 | – | – | – |
| pg_6 (1800 s) | #125 | feasible (empty incumbent) | -67923.96 | 0 | 0 | – | – | – |
| pg_6 (600 s, SA seed) | 86cd4d9 | optimal | 67923.96 | 427 | 67923.96 | 0 | 0 | 0 |
| pg_6 (600 s, SA seed) | #125 | optimal | 67923.96 | 427 | 67923.96 | 0 | 0 | 0 |

Reading: every MILP plan of this branch has 0 landing overloads per slot and 0 landing penalties under the heuristics' `evaluate_schedule`, and still replays with 0 playback sequencing violations; 86cd4d9 plans overloaded landings in every case with a solution (tiny7 12, small21 49–72, ka_6 12–27). Objectives drop where landings bind (tiny7 capacity-1 landings: optimum 4388.082752 → 279.796036, delivered 4414.70 → 2360.56 m³; small21 600 s 15645.73 → 11433.31). On the 3-shift Jaffray scenarios the landing-feasible optimum equals the unconstrained one: seeded with the SA plan (1500 iterations, seed 1: ka_6 30913.36, pg_6 67923.96, 0 overloads, 0 violations) both versions accept the start and prove it optimal in 57–86 s, i.e. SA and MILP now agree on value *and* on landing feasibility. Trade-off: unseeded HiGHS no longer finds a first incumbent on ka_6 within 1800 s (86cd4d9 reached its landing-violating optimum after 1056 s); pg_6 had no unseeded incumbent before either; med42 has none at 120/600 s in either version. The non-landing heuristic penalties of MILP plans (not shown; e.g. tiny7 4, small21 16–21) come from `evaluate_schedule` proposing full rates where the MILP planned partial production; playback, which replays the planned production, reports 0 violations.

Unchanged: reference ladder (`fhops bench suite`, committed flags, into a temp dir) — tiny7 SA ×3 /
ILS / Tabu and small21 SA ×3 / ILS / Tabu rows and every assignment CSV byte-identical; SoftwareX
playback assets (`run_playback_analysis.py`): all 48 generated files byte-identical.

Hand-off (not changed, pre-existing): `evaluate_schedule` charges 1000 for every unavailable
machine slot whether or not it is assigned (a constant offset in heuristic objectives of scenarios
with `available = 0` calendar entries; none in the shipped or Jaffray scenarios) — the shipped
synthetic tiers do have such slots: 22/133/335). Fixed in #131 (§8.21 item 10).

### 8.21 Exact heuristic objective (stale mobilisation cache) (#131)
Follow-up to the §8.16 finding (SA/ILS/Tabu report more than a fresh `evaluate_schedule` of their
exported schedule). Branch `issue-131-heuristic-objective-cache`; scratch in `/tmp/opencode/w131/`
(`repro.py`, `check_all.py`, `idem.py`, `evalbench.py`, `prof.py`, `bench/`). Code part only; the
SoftwareX asset regeneration follows after all Phase 8 code has merged.

1. **Root cause (cache).** Every operator returns `context.sanitizer(candidate)`, and the sanitizer
   (`OperationalProblem.build_sanitizer`) builds a *new* `Schedule(plan=…)`: the copied
   per-machine mobilisation cache and dirty set of `_clone_schedule` are discarded. The repair
   passes (`generate_neighbors` → `fill_voids=False`, then `evaluate_schedule`) call
   `_set_assignment`, which adds only the machines whose slots they **change** to
   `dirty_machines`. `_ensure_mobilisation_stats` filled the whole cache only when the cache *and*
   the dirty set were both empty; otherwise it recomputed just the dirty machines. Every machine
   the repair left untouched therefore had no cache entry, and `evaluate_schedule` summed
   mobilisation cost and transitions over the cache only → those machines' moves were free in the
   score. The greedy seed (`init_greedy_schedule` computes all machines) and plans rebuilt from
   assignments (`_assignments_to_schedule`, empty cache and dirty set) were scored correctly,
   which is why fresh evaluations of the exported CSVs were lower and why runs whose best schedule
   was the seed show no gap (synthetic_small: SA never improves on the seed). Minimal reproduction:
   a plan-only `Schedule` with one machine dirty →
   `_ensure_mobilisation_stats` → one cache entry (`tests/heuristics/test_objective_exact.py::
   test_mobilisation_cache_covers_machines_missing_from_cache`); end to end, tiny7 SA 100 iters
   seed 42 reported 4306.522752 vs fresh 4295.774752 (`repro.py`), and the regression fixture
   (`tests/fixtures/regression`) scored −999.5 instead of −1005.5 (F1's B1→B2 move, 1 + 5, missing).
2. **Tabu was not immune.** It was affected on tiny7 (+10.748) and small21 (+151.144). med42
   showed 0 because Tabu scored its *initial* schedule with dirty-slot repairs regardless of
   `use_local_repairs` (that pass only revisits assigned slots, so idle slots stay empty:
   med42 seed score −38624.19 vs −55619.93 with the full repair SA/ILS use). No neighbour beat
   that inflated seed score, so Tabu never improved (`improvements = 0`, 1 restart, verified on the
   old code for 50/400 iterations with batch 6) and its reported result was simply the full
   re-score of the greedy seed (complete cache) → −46063.73, gap 0.
3. **Second source: repair not idempotent on multi-shift days.** "Fresh evaluation" repairs the
   plan again. On single-shift days the full repair is idempotent (by induction over slots: each
   kept/selected block was valid in the same state). The #116 landing guard broke this on
   multi-shift days with `landing_surplus = 0`: `landing_has_room` counted the machines the repair
   had not reached yet in that slot with their *pre-repair* blocks, so re-repairing a repaired plan
   changed it (three-shift test scenario: 23 slots changed by the second pass, score −22439.0 →
   −22827.5; `idem.py`). Machines not yet reached now count only through their locks (fixed for
   every pass), so the repair reaches a fixpoint in one pass (second pass: 0 changes) and the score
   of a repaired plan equals its fresh evaluation.
4. **Third source: idle locked slots.** The repair validated locked slots (`enforce_prereq=False`)
   and replaced a lock whose block had no remaining demand (e.g. a rolling user lock on a block an
   earlier window finished) with another block; `evaluate_schedule` then charged a 1000 lock
   penalty. With the exact objective the SA trajectory in
   `tests/planning/test_rolling_carry_forward.py::test_user_locks_survive_all_iterations[sa]`
   finishes B1 before its day-5 lock and the lock was lost. Locked slots are now kept as planned
   (an idle locked slot produces nothing; `evaluate_schedule` scores the locked block anyway).
5. **Fix** (`heuristics/common.py`, `sa.py`, `ils.py`, `tabu.py`):
   - `_ensure_mobilisation_stats` recomputes dirty machines **and** machines without a cache entry
     and drops entries for machines not in the plan; `evaluate_schedule` sums mobilisation in
     scenario machine order (independent of cache insertion order / string hashing).
   - `landing_has_room` ignores the pre-repair blocks of machines not yet reached (locks count);
     locked slots are not re-validated by the repair.
   - Tabu scores its initial schedule with `use_local_repairs` (full repair by default), like SA/ILS.
   - SA/ILS/Tabu report `objective` = `rescore_fresh(...)`: a full evaluation of a cache-free copy
     of the best plan, and export that copy (`meta["best_score"]`, telemetry, watch and the SA
     `schedule` use it). With items 1–4 this equals the score the search held.
   - `use_local_repairs=True` (Python API only, not used by the CLI or any asset) stays an
     approximate mode: its dirty-slot repair does not refill idle slots, so a candidate's score is
     exact for the plan it holds but a full repair could still change that plan; the reported
     objective is exact. Documented in the three docstrings.
6. **Tests.** `tests/heuristics/test_objective_exact.py`: minimal reproduction; hypothesis
   property test (seeded random operator sequences of up to 12 moves with random accept/reject on
   tiny7, tiny7 + lock + `initial_state`, small21 and a 3-shift scenario with mobilisation for every
   machine, day- and shift-level locks, block/machine `initial_state`, a blackout day and an
   unavailable shift): after every move the candidate's score equals a fresh evaluation of a
   cache-free copy (and that copy's plan is unchanged by the repair), every cache entry equals a
   recompute, and the kept schedule re-scores to its cached value; a `_ScoreAudit` that wraps
   `evaluate_schedule` and checks **every** score SA (sequential and batched), ILS (incl. a real
   HiGHS hybrid step) and Tabu compute; reported objective = `evaluate_schedule` of the exported
   assignments (also with `watch_debug` and `use_local_repairs`); Tabu initial score = SA's; idle
   locked slot kept. Locally run with `max_examples=60` (committed: 8). Updated pins:
   `tests/initial_state/test_v100_regression.py` (SA tiny7 300/123 and med42 150/7 no longer
   reproduce v1.0.0 → new `*_v101.csv` + `sa_objective_v101`/`kpis_v101` in `baseline.json`, with
   reported = fresh and new fresh > v1.0.0 fresh asserted; the v1.0.0 CSVs stay as KPI fixtures
   and a new test pins their fresh objective below the v1.0.0 report: tiny7 4295.774752 vs
   4306.522752, med42 −39268.927316 vs −38434.227316); `tests/fixtures/regression/baseline.yaml`
   objective −999.5 → −1005.5 (same plan; the test now also asserts reported = fresh), then −5.5 with item 10.
7. **Performance.** Recomputing every machine per candidate is O(machines × slots), the same
   order as the tracker pass; the repair dominates. cProfile, SA 500 iters (tiny7) / 100 iters
   (med42), seed 42: `_recompute_mobilisation_for` 14266 → 18026 calls on tiny7 (3466 → 4526 on
   med42), 1.0 → 1.1 % (tiny7) and 0.7 → 0.4 % (med42) of runtime;
   `_repair_schedule_cover_blocks` ≈ 63 % before and after. Fixed workload (`evalbench.py`: neighbours of the greedy seed generated
   and evaluated, same RNG, best of 3, two rounds each, machine load ≈ 170 on 72 cores so ±25 %
   noise): tiny7 700/796 → 926/904 candidates/s, small21 158/188 → 239/202, med42 85/84 → 77/74.
   No measurable change; no incremental shortcut was needed.
8. **Old vs new** (committed `generate_assets.sh` settings, `fhops bench suite` into
   `/tmp/opencode/w131/bench/new/<scenario>_<sa|ils|tabu>`; "old" = committed assets, reproduced
   exactly on 1.0.1 in §8.16; "old fresh" = `evaluate_schedule` of the committed CSV). New reported
   = new fresh for every row (checked to 1e-9).

   | scenario | solver | preset | old reported | old fresh | new reported = fresh | Δ fresh | production old → new | mobilisation old → new | assignments old → new | penalty old → new | runtime s old → new | same plan |
   |---|---|---|---|---|---|---|---|---|---|---|---|---|
   | tiny7 | sa | default | 4306.523 | 4295.775 | 4295.775 | +0.000 | 4414.70 → 4414.70 | 585.64 → 585.64 | 23 → 23 | 0 → 0 | 33 → 36 | yes |
   | tiny7 | sa | diversify | 4306.523 | 4295.775 | 4295.775 | +0.000 | 4414.70 → 4414.70 | 585.64 → 585.64 | 23 → 23 | 0 → 0 | 15 → 16 | yes |
   | tiny7 | sa | mobilisation | 4306.523 | 4295.775 | 4295.775 | +0.000 | 4414.70 → 4414.70 | 585.64 → 585.64 | 23 → 23 | 0 → 0 | 32 → 46 | yes |
   | tiny7 | ils | - | 4349.265 | 4338.517 | 4338.517 | +0.000 | 4414.70 → 4414.70 | 372.68 → 372.68 | 23 → 23 | 0 → 0 | 46 → 33 | yes |
   | tiny7 | tabu | - | 4349.265 | 4338.517 | 4338.517 | +0.000 | 4414.70 → 4414.70 | 372.68 → 372.68 | 23 → 23 | 0 → 0 | 293 → 204 | yes |
   | small21 | sa | default | 15627.571 | 15562.603 | 15584.157 | +21.554 | 15966.97 → 15966.97 | 1977.32 → 1871.80 | 90 → 90 | 0 → 0 | 78 → 97 | no |
   | small21 | sa | diversify | 15616.925 | 15562.945 | 15562.945 | +0.000 | 15966.97 → 15966.97 | 1976.36 → 1976.36 | 90 → 90 | 0 → 0 | 28 → 41 | no |
   | small21 | sa | mobilisation | 15627.781 | 15573.753 | 15593.845 | +20.092 | 15966.97 → 15966.97 | 1924.32 → 1823.36 | 90 → 90 | 0 → 0 | 78 → 113 | no |
   | small21 | ils | - | 15638.083 | 15573.355 | 15605.943 | +32.588 | 15966.97 → 15966.97 | 1924.56 → 1764.12 | 90 → 90 | 0 → 0 | 86 → 71 | no |
   | small21 | tabu | - | 15660.009 | 15508.865 | 15595.283 | +86.418 | 15966.97 → 15966.97 | 2243.76 → 1815.92 | 90 → 90 | 0 → 0 | 415 → 280 | no |
   | med42 | sa | default | -27271.221 | -30331.841 | -28662.400 | +1669.442 | 32071.86 → 31793.02 | 10564.68 → 10110.44 | 211 → 209 | 51000 → 49000 | 1245 → 1625 | no |
   | med42 | sa | diversify | -30977.726 | -31815.426 | -33965.984 | -2150.559 | 32297.03 → 32119.53 | 10432.52 → 10023.64 | 210 → 212 | 53000 → 55000 | 419 → 483 | no |
   | med42 | sa | mobilisation | -26565.270 | -29654.070 | -29188.831 | +465.239 | 32426.04 → 32028.43 | 10625.84 → 10104.92 | 210 → 210 | 51000 → 50000 | 1242 → 1664 | no |
   | med42 | ils | - | -33452.282 | -35484.182 | -33253.410 | +2230.772 | 33025.19 → 31538.89 | 10682.68 → 10275.92 | 213 → 209 | 58000 → 53000 | 1792 → 831 | no |
   | med42 | tabu | - | -46063.733 | -46063.733 | -41009.666 | +5054.066 | 30026.28 → 31556.20 | 9846.12 → 9857.68 | 212 → 208 | 63000 → 61000 | 7391 → 3596 | no |

   tiny7: the committed plans were already optimal for the exact objective (byte-identical CSVs);
   only the reported objective drops to the plans' fresh value (−10.748). small21: equal delivery,
   lower mobilisation, fresh objective +20…+86 (SA diversify ends on an equivalent plan). med42:
   fresh objective better for SA default/mobilisation, ILS and Tabu (Tabu now searches at all:
   −46063.73 → −41009.67); SA diversify ends 2150.56 lower (a different stochastic trajectory under
   the diversify preset, not a scoring error: its reported value equals its fresh value). "penalty"
   = 1000-point penalties of the plan (`evaluate_schedule` debug `penalty_total`). Runtimes are
   not comparable (the machine ran ~170 load on 72 cores during the new runs).

   Jaffray scenarios (read-only, three shifts, no mobilisation config, transitions not weighted),
   SA 1500 iterations, seeds 1–3, old → new: ka_6 30913.355595 ×3 → 30913.355595 ×3 (277
   assignments, delivered 30913.36 m³, 0 sequencing violations, reported = fresh before and after);
   pg_6 67923.9629 ×3 → 67923.9629 ×3 (427 assignments). Only the last floating-point bit changes
   (summation order). These objectives have no mobilisation/transition term, so the cache defect
   never applied, and the landing-guard change does not change the SA objective here.
9. **Merge with #132 (6597a7a).** `optimization/heuristics/` was not touched by #132 (its landing
   alignment is MILP-side: per-slot E11, hard at `landing_surplus = 0`, `k·ω` pieces matching the
   heuristics' `e(e+1)/2`; day locks expanded in rolling/MILP; tracker idle slots), so the merge was
   conflict-free in code; CHANGE_LOG, ROADMAP and release notes had add/add conflicts (both entries
   kept). Semantics combine as follows: the heuristic `lock_for` already returns a day lock for every
   slot of its day and the repair clears unavailable slots (§8.18 item 2), which is what the MILP's
   expansion does; locked slots are still kept on their block (#131) and landing capacity counts
   machines not yet reached in the slot only through their locks (#131). Re-checks on the merge:
   `test_objective_exact.py`, `test_milp_landing_capacity.py`, `test_rolling_day_locks.py`,
   `test_idle_locked_slot.py`, `test_rolling_robustness.py`, `test_rolling_carry_forward.py` pass;
   #132's MILP plans (`/tmp/opencode/w125/post.py`, `evaluate_schedule` without repair) score
   identically on 6597a7a and on this branch with 0 landing penalties (tiny7 60 s −3746.82,
   small21 120 s −19191.58 / 600 s −5450.91, ka_6 / pg_6 SA-seeded 30913.36 / 67923.96), and a
   fresh tiny7 MILP solve on the merge (optimal 279.796036) also has 0 landing penalties;
   `audit_asset_consistency.py` pass/fail results unchanged (all OK on 6597a7a and here; only the
   informational synthetic/scaling `full_eval_objective` columns move, see item 10).
10. **Unavailable-slot offset (hand-off from §8.18).** `evaluate_schedule` added 1000 for every
   machine slot that is unavailable in the shift or day calendar or blacked out, *before* checking
   whether anything was assigned, so every such slot cost 1000 even when idle: a constant offset (no
   effect on search decisions, since the SA start temperature `max(1, score/10)` is 1 for these
   negative objectives either way). Now only an *assigned* unavailable slot is penalised (the repair
   clears those before scoring, so repaired plans pay nothing). Affected scenarios
   (`/tmp/opencode/w131/unav.py`, unavailable machine-slots): synthetic small 22 / 224, medium
   133 / 448, large 335 / 672, the regression fixture 1 / 8; tiny7, small21, med42, large84 and all
   Jaffray scenarios (ka/ni/pg × 6/18/40) have none, so their results are unaffected.
   Synthetic-small −75039.791 → −53039.791 (+22000; re-run with committed settings into
   `/tmp/opencode/w131/bench/new2/`: SA ×3, ILS and Tabu assignment CSVs byte-identical to the
   committed ones; SA initial score +22000; Tabu's operator counts differ because its seed is now
   scored with the full repair, item 2, but it ends on the same plan); the scaling
   sweep's committed objectives −75039.79 / −261097.03 / −359224.71 re-evaluate to −53039.79 /
   −128097.03 / −24224.71 (they change on regeneration). Regression fixture −1005.5 → −5.5. Test:
   `test_idle_unavailable_slots_are_not_penalised` (calendar day + blackout day idle → penalty 0,
   objective 20, SA reports 20; v1.0.0: −1980).
11. **Re-run after the merge and item 10** (`bench/new2/`, same commands as item 8): tiny7 SA ×3 /
   ILS / Tabu and small21 SA ×3 / ILS / Tabu summary rows identical to the item 8 table in every
   non-runtime column and every assignment CSV byte-identical — the PR table stands.

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
