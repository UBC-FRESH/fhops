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

### 8.6 Release and forward-port (#96)
Version `1.0.1`; release notes in `docs/releases/v1.0.1.md`; Hatch build, clean-venv smoke,
TestPyPI → PyPI, annotated tag `v1.0.1`, GitHub release. Forward-port the fixes to `main` (next
1.1.0 alpha) via a PR, resolving ROADMAP/CHANGE_LOG conflicts.

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
