# Rolling-Horizon Replanning Plan

> **Purpose:** introduce a rolling-horizon replanning workflow so FHOPS can emit multi-month "locked" schedules by solving a sequence of tractable subproblems. This note captures scope, assumptions, architecture, and implementation phases before we start cutting code.

## Goals
- Produce an initial implementation that focuses on planning machinery (scenario slicing, lock-in enforcement, horizon advancement).
- Keep evaluation/reporting hooks in mind for follow-up work so MASc-led studies can measure suboptimality patterns vs. full-horizon baselines.
- Deliver both CLI and Python API surfaces that orchestrate the rolling-horizon loop with configurable master horizon, subproblem horizon, and lock-in window lengths.

## Key Concepts
- **Master horizon (M days):** total planning length the contractor expects (e.g., 12–16 weeks). Med42 serves as the immediate benchmark; seasonal ladders follow once assets exist.
- **Subproblem horizon (H days):** window solved at each iteration (e.g., 14 or 28 days). Must be ≥ lock window.
- **Lock window (N days):** number of leading days to freeze after each subproblem solve (e.g., 7 days). Locked assignments/mobilisation decisions become immutable context for subsequent solves.
- All horizons must fit inside ``Scenario.num_days`` (``master_days`` + ``start_day`` − 1 ≤ num_days); adjust values or pick a longer scenario.
- **State roll-forward:** after locking N days, advance scenario clocks by N days, shift remaining demand, and rebuild the subproblem with updated calendars/inventories.

## Assumptions & Constraints
1. Locked segments are immutable to keep the rolling horizon tractable. We will monitor feasibility; if evidence arises that limited flexibility is required, document and extend the design.
2. Overall feasibility takes priority. On infeasible subproblems we will start with the simplest robust behavior (e.g., abort with diagnostics or relax lock size) and iterate once gaps surface.
3. Planning machinery first; evaluation/reporting layers (gap analysis, telemetry summarizers) land in later milestones but should be anticipated in the data we log.
4. CLI entry (e.g., `fhops plan rolling ...`) and user-facing Python API (`fhops.planning.rolling.solve(...)`) must share the same engine.

## Proposed Architecture
1. **Scenario slicer:** utility that, given a base scenario + current day offset, produces a truncated subscenario with adjusted calendars, remaining block demand, and carry-forward mobilisation states.
2. **Lock-in tracker:** persists assignments, mobilisation moves, and derived inventories for locked days; feeds them back as boundary conditions/constraints in subsequent solves.
3. **Rolling orchestrator:** drives iteration: solve subproblem → validate → append locked slice to master plan → roll window → repeat until total locked span ≥ master horizon or scenario exhaustion.
4. **Persistence & telemetry:** store per-iteration summaries (objectives, runtime, lock span, infeasibility reasons) so later evaluation layers can compute suboptimality envelopes without re-running solves.
5. **CLI/API surfaces:**
   - CLI: `fhops plan rolling --scenario ... --master-days 112 --sub-days 28 --lock-days 14 --solver sa|mip|auto ...`
   - API: `from fhops.planning import rolling; rolling.solve(config)` returning a structured result (locked assignments, per-iteration stats, warnings).

> **2026-10-06 correction (Phase 8.2, #92 / #90).** The v1.0.0 release ticked the slicer and
> lock-in tracker items below, but no state was actually carried between windows: every window
> re-planned each block's full `work_required` (finished blocks included), staged inventory, role
> progress and head-start counts reset, machines had no initial position, user
> `locked_assignments` were overwritten with `[]` by the hooks, locks dropped `shift_id`
> (duplicate `(machine, day)` locks on multi-shift scenarios), blackouts were not rebased, SA
> `runtime_s` was always `None`, and the MILP hook passed `solver="auto"` to Pyomo unchanged.
> FHOPS 1.0.1 fixes this: `carry_forward_state` replays the stitched locked plan on the base
> scenario with the playback sequencing tracker and the slicer applies the result as
> `work_required` + `Scenario.initial_state` (#91); user locks are merged into every window;
> blackouts are rebased; locks keep `shift_id`. See `notes/v101_maintenance_plan.md` §8.2 and
> `docs/howto/rolling_horizon.rst`. Rolling results produced with v1.0.0 must be regenerated.

## Implementation Phases
- [x] Planning groundwork (this note).
- [x] Core orchestration engine
  - [x] Scenario slicer that trims calendars, demand, and mobilisation state given a day offset + sub-horizon. *(v1.0.0 trimmed calendars only: demand was not reduced and blackouts were not rebased. Fixed in 1.0.1, #92: remaining volume, rebased blackouts, merged user locks.)*
  - [x] Lock-in tracker dataclasses for assignments, mobilisation decisions, and inventories; apply as boundary conditions in subsequent solves. *(Not implemented in v1.0.0 — only assignments were stitched. Implemented in 1.0.1, #92: `carry_forward_state` → `initial_state` with staged inventory, role remaining/shift counts and machine positions.)*
  - [x] Rolling loop that solves → locks N days → advances the window until the master horizon is covered; start with SA baseline and MILP hook stub.
  - [x] Feasibility guardrails (detect infeasible subproblems, surface diagnostics, and optionally relax lock size as a fallback).
- [x] CLI + API exposure
- [x] Typer command `fhops plan rolling` with flags for master/sub/lock horizons, solver choice, seeds, and output paths (stub + SA hook; MILP to follow).
- [x] Python API helper (`fhops.planning.solve_rolling_plan` + `get_solver_hook`) with shared config/response dataclasses. MILP hook now wired (solver=`mip`, `--mip-solver`, `--mip-time-limit`).
- [x] Basic docs/usage strings to unblock early adopters (full docs later).
- [x] Telemetry/logging
  - [x] Per-iteration summaries (objective, runtime, lock span, infeasibility flags) persisted to JSON-ready dicts.
  - [x] Hook telemetry into CLI/API surfaces with consistent schema for future evaluation/reporting layers (`--out-json`, `--out-assignments` exports; fuller reporting still pending).
- [x] Evaluation/reporting extensions
  - [x] Playback/KPI comparison helpers to quantify suboptimality vs. single-horizon baselines (`rolling_assignments_dataframe`, `compute_rolling_kpis`, `comparison_dataframe`, CLI export wiring, and the refreshed how-to doc).
  - [x] Plots/tables for MASc experiments (suboptimality vs. master horizon, sub-horizon, and lock size); tiny7 comparison artifacts generated at `docs/assets/rolling/masc_comparison_tiny7.{csv,png}` (SA baseline 7/7/7 vs. 7/5/3 and 7/4/2, 300 iters, seed=99). Med42 comparison (Gurobi, 64 threads, 10 s caps) generated at `docs/assets/rolling/masc_comparison_med42.{csv,png}` — runs return aborted-with-solution statuses due to the aggressive cap; rerun with larger budgets for publication-ready gaps.

## Edge Cases & Open Questions
- ~~Handling mobilisation/landing buffers that span lock boundaries—verify whether loaders staged in the locked window constrain future days automatically or require explicit inventory carry-over.~~ They did not (v1.0.0); explicit carry-over via `Scenario.initial_state` landed in 1.0.1 (#91/#92).
- Window objectives have no end-of-window valuation of staged inventory, so very short sub-horizons (shorter than the harvest-system pipeline) can plan no upstream work (tiny7 MILP 7/3/1 delivers nothing). Documented as a limitation in `docs/howto/rolling_horizon.rst`; a terminal-value term is a possible follow-up.
- The operational MILP does not model `timeline.blackouts` (heuristics do); rebased blackouts therefore only constrain SA/ILS/Tabu windows.
- Infeasible subproblems after locking: initial plan is to fail fast with actionable diagnostics; subsequently consider auto-adjusting lock window or invoking repair heuristics.
- Interaction with warm-start MILP runs: locked assignments should become incumbent seeds to reduce solve time for overlapping machines/blocks.
- Scaling to season-length horizons will require synthetic dataset refreshes; document those prerequisites alongside med42 validations.

## Next Steps
- [x] Add feasibility guardrails (detect infeasible subproblems; consider relaxing lock span).
- [x] Wire the rolling loop into CLI/API surfaces with a solver hook (SA/MILP done) and add a Python API helper.
- [x] Add telemetry schema so evaluation features can consume per-iteration stats.
- [x] Extend docs with evaluation/reporting guidance and run comparative experiments (MASc deliverable).
  - [x] Add evaluation/reporting guidance to ``docs/howto/rolling_horizon.rst`` (compute_rolling_kpis / evaluate_rolling_plan snippets).
  - [x] Run comparative experiments and capture plots/tables for MASc write-up (tiny7 SA bundle + med42 Gurobi bundle with short caps, both published under ``docs/assets/rolling``; rerun med42 with larger budgets for cleaner gaps).
- [x] Add playback/KPI helpers to consume rolling exports and quantify suboptimality vs. single-horizon baselines.
- [ ] Run full-suite regression on rolling horizon scenarios once post-merge validation slots open (long-running).
