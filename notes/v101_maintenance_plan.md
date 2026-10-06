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
`load_scenario` attaches YAML `locked_assignments` via `model_copy`, so they skip cross-validation.

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

### 8.4 Units docs (#94)
`Block.work_required` documented as m³ (terminal delivered volume) in the contract docstring,
data-contract docs, and the loader/playback docs; no behaviour change.

### 8.5 SoftwareX figure and assets (#95)
- `docs/softwarex/manuscript/scripts/plot_playback_variability.py`: column-width figure size,
  ≥ 9 pt fonts at print size, legend inside the canvas (no clipping, no suptitle), upper-case
  solver labels.
- Regenerate playback assets with the fixed events (`run_playback_analysis.py`) and record the
  benchmark log. Deterministic benchmark/tuning/scaling assets must be unchanged.

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
