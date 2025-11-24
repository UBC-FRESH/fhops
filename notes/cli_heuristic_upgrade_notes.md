# FHOPS CLI – Heuristic Monitor Upgrade Notes

## Motivation
- Current `fhops bench suite` runs are opaque until they finish; we only see results via `summary.(csv|json)` or telemetry files.
- For long heuristic runs (SA/ILS/Tabu with large `iters` or multi-worker setups) we need real-time feedback to spot stalls, divergence, or budget issues.
- We already emit per-iteration telemetry (objective, accepted moves, runtime); exposing a subset live would help diagnose convergence and demonstrate progress to users.

## Watch Mode Concept
1. `--watch` flag on `fhops bench suite` (and optionally `fhops tuning run`) that:
   - Streams key metrics (best objective, delta vs. MIP baseline, acceptance rate, runtime elapsed, iterations completed).
   - Supports multi-solver runs by giving each solver its own panel/row.
   - Respects existing JSONL logging (no change to telemetry schema).
2. Optional `--watch-refresh <seconds>` (default ~0.5s) to control UI update cadence.
3. Detect non-interactive terminals and fall back to terse log lines (no live rendering).

## Implementation Sketch
- Leverage Typer’s Rich integration: Typer already bundles Rich console; we can import `rich.live.Live` or `rich.progress.Progress` for streaming output.
- Architecture:
  1. Heuristic runners publish periodic snapshots (e.g., via a `Queue` or callback) containing the latest telemetry chunk.
  2. Watcher task (async or background thread) consumes snapshots and updates live layout.
  3. On completion, watcher renders final summary and exits cleanly (restoring cursor).
- Candidate metrics to display per solver:
  - `best_objective` + gap vs. user-supplied target or latest MIP run.
  - `iterations_completed / max_iters`, acceptance rate, restarts triggered.
  - Wall-clock runtime vs. allotted budget (time limit).
  - Worker utilisation (if multi-threaded heuristics expose progress).
- For tuning sweeps, aggregate per-trial progress into a table (trial ID, solver preset, current best objective, runtime, status).

## Library Options
- `rich.progress.Progress`: good for per-solver progress bars with custom columns (objective, gap, runtime).
- `rich.live.Live`: better for custom grid/panel layout (multiple metrics, textual spark-lines).
- `rich.table.Table`: display final snapshot after run completes.
- Use `rich.console.Console(status=...)` for textual spinner fallback when `--watch` omitted.

## Multi-Phase Implementation Plan

### Phase 1 – Design & Prototyping
- [ ] **Watcher API spec**
  - [x] Draft a `fhops.telemetry.watch` module describing `Snapshot` dataclass (scenario, solver, iter, objective, best_gap, runtime, acceptance_rate, restarts, workers_busy).
  - [x] Decide on transport: callback registry vs. `queue.Queue` per solver; ensure thread-safety for multi-worker heuristics.
  - [x] Define `WatchConfig` (refresh interval, render mode, quiet fallback).
- [ ] **Rich Live prototype**
  - [x] Build a standalone script that tails an existing telemetry JSONL file and feeds rows into the watcher layout (simulate SA progress).
  - [x] Validate Rich refresh cadence, color palette, terminal width handling, and fallback text mode when `isatty` is false.
- [ ] **Testing hooks**
  - [x] Add unit tests for `Snapshot` serialization/deserialization and gap calculations.
  - [x] Create a regression fixture with synthetic telemetry to ensure the watcher summary math (best objective, runtime) matches expectations.

### Phase 2 – CLI Integration
- [ ] **Flags & plumbing**
  - [x] Add `--watch/--no-watch` and `--watch-refresh` to `fhops bench suite`.
  - [x] Mirror the watch flags on tuning commands (grid/random/bayes runners).
  - [x] Detect TTY capability; auto-disable watch when output is redirected.
- [ ] **Solver instrumentation**
  - [x] Update SA runner to emit snapshots at configurable cadence (ILS/Tabu pending).
  - [x] Ensure multi-worker heuristics aggregate metrics (per-worker iter counts, acceptance rates) before emitting.
      - Batch scoring now tracks `workers_busy/workers_total` in SA/Tabu snapshots so the dashboard reflects how many threads the run actually occupies; revisit ILS if/when we add parallel evaluation there.
  - [x] Thread watch hooks through `solve_ils` and `solve_tabu`, including heuristic-specific metrics (perturbations, tabu tenure, stall counters) and expose the same dashboard via CLI + bench runners.
  - [x] Expose SA cooling rate and restart-interval knobs (solver + CLI + benchmarks) so long runs cool gradually instead of collapsing into hill-climbs.
  - [x] Teach Tabu to diversify instead of exiting when stalls exceed the limit (clear tabu list, restart counters, propagate accurate restart telemetry/watch metrics).
  - [x] Regenerate the `med42` sample dataset so block areas fall within Lahrsen (2025) ranges (0.8–2.6 ha, 160–320 m³/ha) and rescale production/KPI fixtures accordingly.
  - [ ] Document that `--parallel-workers` currently uses threads (GIL-bound) so it only helps when operators release the GIL; recommend `--parallel-multistart` or external orchestration for true multi-core runs until the scoring loop is parallelized properly.
  - [x] Capture current best-performing ILS tuning baseline for med42: `iters=40_000`, `perturbation_strength=1`, `stall_limit=100`, single-threaded workers. These values keep restarts at zero and yield the observed 34.5 objective while the watcher trend remains stable. Keep this as a reference preset when refining Phase 2 heuristics.
- [ ] **UI enhancements**
  - [x] Display both current objective and best-so-far so flat lines still show ongoing exploration.
  - [x] Add a lightweight “Z sparkline” (objective vs. iteration) per solver row using a rolling history so improvements are visible in real time.
  - [x] Surface solver internals: current temperature, rolling-window objective mean, sliding-window acceptance rate, and per-refresh improvement rate/delta so users can gauge convergence speed.
  - [x] Refactor columns so shared metrics (scenario/solver/iter/best/curr/roll/runtime) stay consistent across solvers, while solver-specific data (e.g., SA temperature/acceptance, ILS perturbations, Tabu tenure/stalls) render in dedicated per-solver detail rows.
  - [x] Move the sparkline trend out of the main table (render below each row) to avoid column jitter and provide more horizontal resolution.
- [ ] **Graceful teardown**
  - [x] Flush remaining snapshots on stop so short-lived runs still render a final state.
  - [x] Trap `KeyboardInterrupt` so the live display stops cleanly and the final snapshot is printed (bench suite now wraps watch mode in a `try/finally`; other commands already run the watch context via `with` blocks).
  - [ ] Confirm telemetry logging + JSON outputs remain unchanged.
- [ ] **Testing**
  - [ ] CLI integration tests (pytest) that run a small SA benchmark with `--watch` enabled but using Rich “console recorder” to verify text output contains live sections.
  - [ ] Smoke test for tuning harness watch mode (reduced budget) to ensure multiple concurrent trials render without crashing.
  - [x] Add regression coverage for ILS/Tabu watch mode hooks once instrumentation lands.

### Phase 3 – Documentation & Support Material
- [ ] **User docs**
  - [ ] Update `README.md` + `docs/howto/benchmarks.md` with a “Watching heuristics” section covering flags, sample output, and troubleshooting.
  - [ ] Add an FAQ entry about disabling watch in non-interactive environments.
- [ ] **Manuscript/Sphinx snippets**
  - [ ] Capture a screenshot or short GIF of the Rich dashboard for both the SoftwareX manuscript and Sphinx docs (assets under `docs/softwarex/assets/figures/cli_watch_demo.{png,pdf}`).
- [ ] **Tutorial notebook**
  - [ ] Extend `docs/examples/analytics` with a short notebook showing how watch mode helps diagnose convergence (embed static output).
- [ ] **Testing & CI**
  - [ ] Add a regression test to ensure watch mode doesn’t break `make manuscript-benchmarks` (run a bench job with `FHOPS_WATCH=0` to suppress UI).
  - [ ] Consider a GitHub Actions job that runs the prototype with `rich.console.Console(record=True)` to guard against formatter regressions.

### Phase 4 – Feedback & Iteration
- [ ] **Power-user feedback**
  - [ ] Share the feature with lab partners; gather feedback on useful metrics (e.g., temperature schedule, last improving move).
- [ ] **Feature toggles**
  - [ ] If users request more detail, add optional panels (telemetry sparkline, per-worker histograms) gated behind `--watch-verbose`.
- [ ] **Performance tuning**
  - [ ] Stress-test on 24/48-core runs to ensure watch rendering overhead stays <1 % of runtime.
- [ ] **Future ideas**
  - [ ] Consider WebSocket/TTY streaming to send snapshots to remote dashboards.
  - [ ] Explore storing watcher snapshots in structured logs for post-hoc playback.
