# Documentation Plan (FHOPS)

Date: 2025-12-12  
Status: Working draft — replaces `cli_docs_plan.md` and `pr_note_mip_warm_start_docs.md` as the consolidated docs roadmap.

## Objectives
- Deliver self-directed, beginner-to-confident-user documentation across overview, how-tos, API, and CLI.
- Keep CLI ergonomics discoverable (rich help, examples, presets) and aligned with solver/data features.
- Capture solver/MIP nuances (warm starts, solver options, rolling horizons) without requiring code spelunking.
- Maintain developer-facing docs that shorten onboarding and make contribution paths explicit.

## Current Coverage Snapshot
- Sphinx structure in place (overview, how-tos, API, CLI reference); rolling-horizon how-to/API updated.
- Warm-start docs exist (`docs/howto/mip_warm_starts.rst`); CLI exposes solver/warm-start flags.
- Rolling comparison artefacts published: tiny7 (SA) and med42 (Gurobi 64 threads, 10 s cap) CSV/PNG under `docs/assets/rolling/`.
- Shift-aware docs partially covered; more examples/validation steps still needed.

## Developer-Facing Documentation (onboarding & ergonomics)
- Provide a “New contributor quickstart” linking: repo layout, env setup (python/poetry/venv), test/lint commands, data fixtures, and common scripts.
- Add “How to read the code” guide (module map: scenario → problem → solver → playback → KPIs; key entry points).
- Document debug workflows: running single CLI commands with fixtures, enabling solver logs, timing/profiling helpers, and CI gates (e.g., `FHOPS_RUN_FULL_CLI_TESTS`).
- Contribution pathways: small/medium/large task examples, docstring/Sphinx expectations, how to propose docs-only changes.
- Repro/bench guidance: where artefacts live, how to regenerate them, expected runtimes, and hardware notes (Gurobi threads, time limits).

## Outstanding Docs Tasks
- [x] Rolling-horizon user docs
  - [x] Documented `mip_solver_options` (threads/time-limit examples for Gurobi/HiGHS) in how-to + API.
  - [x] Added MILP rolling example (med42) with realistic caps, playback/KPI follow-through, and CLI options for solver threads/time limits.
  - [x] Exposed `comparison_dataframe` in API docs and linked it from the rolling how-to as the plotting/table helper.
  - [x] Added a “Gotchas”/FAQ (master_days guardrail, long MILP runtimes, abort statuses).
- [x] CLI reference polish
  - [x] Expanded `fhops plan rolling` entry with MILP options, telemetry exports, evaluation handoff, and a Gurobi threads example.
  - [x] Aligned solver-option help text with the operational MILP CLI (shared parser).
- [x] Quickstart/onboarding
  - [x] Added a rolling quickstart loop chaining baseline → rolling CLI → KPI deltas/plots; cross-linked to the rolling how-to.
- [x] Artefact provenance
  - [x] Documented rolling artefacts in `docs/assets/rolling/` (solver, threads, time limits, seeds, status) and how to regenerate them; noted the short-cap “aborted with solution” status on med42.
  - [x] Added a “rerun MASc comparisons” snippet with commands and plotting steps.
- [x] Shift-aware docs
  - [x] Added examples with shift calendars/blackouts in quickstart and refreshed CLI reference for shift flags.
  - [x] Provided validation steps comparing day vs shift KPIs for a shift-enabled scenario.
- [ ] API completeness
  - [x] Autosummary includes planning/reporting helpers (`compute_rolling_kpis`, `comparison_dataframe`, `rolling_assignments_dataframe`) and new params (`mip_solver_options`).
  - [x] Audited planning/reporting helpers for NumPy-style docstrings (parameters, returns, notes) so Sphinx renders the updated signatures; keep future edits aligned with this style.
- [x] Developer-specific docs
  - [x] Drafted onboarding playbook (env/test commands, fixtures, data paths, CI expectations) and common pitfalls.
  - [x] Added debugging/profiling guidance (solver logging, Pyomo/Gurobi options, telemetry exports, short caps for smoke tests).

## Legacy Items Rolled In
- Warm-start documentation: keep `docs/howto/mip_warm_starts.rst` aligned with operational MILP changes and note current benefits/limits (med42/large84 gains pending stronger incumbents).
- Shift-aware punch list (from 2025-11-09): extend how-tos/CLI reference, add validation aids and release/CHANGE_LOG hooks when shift updates land.

## Open Questions
- How to present “dev vs release” docs (RTD versioning) without confusing users? *(Deferred; current users are internal/alpha, revisit when audience expands beyond the initial MASc workflow.)*
- Should rolling artefacts ship in repo or be published as downloadable assets for lighter clones? *(Current rolling bundle is small ≈57 KB under `docs/assets/rolling`; keep in-repo for now.)*
- Notebook coverage vs. rendered HTML: which examples must remain executable in CI vs cached? *(Keep notebooks executable in CI unless they are long-running; skip/cache only heavy ones.)*

## Open Tasks (next iteration)
- [ ] Monitor new features for docstring/API coverage; keep planning/evaluation helpers in NumPy style with return schema details.
- [ ] Expand shift-enabled examples when a maintained scenario with real shift calendars is added to the repo; thread it through quickstart, data contract, and CLI reference once available.
